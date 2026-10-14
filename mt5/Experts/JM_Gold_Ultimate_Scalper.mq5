//+------------------------------------------------------------------+
//| JM_Gold_Ultimate_Scalper.mq5                                     |
//| JM GOLD ULTIMATE SCALPER V0.0.2                                  |
//| Dynamic Follow-Price Pending Orders + Profit Trailing           |
//| Chart TP/SL display (Thunder Gold style)                         |
//| Platform: MetaTrader 5 (MQL5)                                    |
//+------------------------------------------------------------------+
#property copyright "JM Tech Solution"
#property version   "0.002"
#property description "Gold scalper: follow-price stops + USD trailing + TP/SL chart display"
#property strict

#include <Trade/Trade.mqh>
CTrade trade;

//---------------- INPUTS ----------------//
input double LotSize             = 0.01;
input double PendingDistance     = 15.0;   // Price distance (confirm on your XAUUSD digits)
input double InitialSL_USD       = 0.15;   // Account currency (USD)
input double TrailingStart_USD   = 0.25;
input double TrailingLock_USD    = 0.15;
input double TrailingGap_USD     = 0.10;
input double MaxSpreadPrice      = 1.00;
input int    UpdateSeconds       = 2;
input ulong  MagicNumber         = 100001;
input int    DeviationPoints     = 30;
input bool   RestartCycle        = false;  // true = clear loss-stop and re-arm (then set false)

input group "Chart display (Thunder style)"
input bool   ShowLevelsDisplay   = true;
input double VisualTP_USD        = 0.25;   // Visual TP only (not sent as order TP)
input color  ClrEntry            = clrDodgerBlue;
input color  ClrSL               = clrTomato;
input color  ClrTP               = clrLime;
input color  ClrPending          = clrGold;
input int    LineWidth           = 2;
input bool   ShowCandleMarkers   = true;

#define OBJ_PREFIX "JM_GUS_"

// No fixed broker TP — VisualTP_USD is chart display only.
// One active position maximum.
// After net-loss exit: cycle stops until RestartCycle or manual GV clear.
// After net-profit exit: re-arm pendings.

//---------------- GLOBALS ----------------//
bool     CycleStopped   = false;
bool     PositionSeen   = false;   // true while our position is open / just filled
ulong    TrackedPosition = 0;
double   PeakProfit     = 0.0;

//---------------- HELPERS ----------------//
string CycleGvName()
{
   return StringFormat("JM_GUS_STOPPED_%s_%I64u", _Symbol, MagicNumber);
}

void SaveCycleStopped()
{
   GlobalVariableSet(CycleGvName(), CycleStopped ? 1.0 : 0.0);
}

void LoadCycleStopped()
{
   if(RestartCycle)
   {
      CycleStopped = false;
      GlobalVariableSet(CycleGvName(), 0.0);
      Print("RestartCycle=true: loss-stop cleared. Set RestartCycle back to false.");
      return;
   }

   if(GlobalVariableCheck(CycleGvName()))
      CycleStopped = (GlobalVariableGet(CycleGvName()) > 0.5);
}

bool TradingAllowed()
{
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      return false;
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      return false;
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
      return false;
   if(!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      return false;

   long mode = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(mode == SYMBOL_TRADE_MODE_DISABLED)
      return false;

   return true;
}

double NormalizePrice(double price)
{
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0)
      tick = _Point;

   return NormalizeDouble(MathRound(price / tick) * tick, _Digits);
}

double VolumeForOrder()
{
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if(step <= 0.0)
      return 0.0;

   if(LotSize < minLot || LotSize > maxLot)
      return 0.0;

   double steps = MathRound((LotSize - minLot) / step);
   double volume = minLot + steps * step;

   if(MathAbs(volume - LotSize) > 0.0000001)
      return 0.0;

   return NormalizeDouble(volume, 8);
}

bool IsOurPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         return true;
   }

   return false;
}

ulong OurPositionTicket()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         return ticket;
   }

   return 0;
}

// Reconcile PositionSeen with live positions (missed IN event / EA restart).
// Cleared only on net OUT (or OnInit while flat) so fill→position gap still blocks re-arm.
void SyncPositionSeen()
{
   if(IsOurPosition())
      PositionSeen = true;
}

void DeleteOurPending()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0)
         continue;

      if(OrderGetString(ORDER_SYMBOL) != _Symbol ||
         (ulong)OrderGetInteger(ORDER_MAGIC) != MagicNumber)
         continue;

      ENUM_ORDER_TYPE type =
         (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);

      if(type == ORDER_TYPE_BUY_STOP ||
         type == ORDER_TYPE_SELL_STOP)
      {
         if(!trade.OrderDelete(ticket))
            Print("Delete failed: ", trade.ResultRetcodeDescription());
      }
   }
}

bool FindPending(ENUM_ORDER_TYPE type,
                 ulong &ticket,
                 double &price,
                 double &sl)
{
   ticket = 0;
   price = 0.0;
   sl = 0.0;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong id = OrderGetTicket(i);
      if(id == 0)
         continue;

      if(OrderGetString(ORDER_SYMBOL) != _Symbol ||
         (ulong)OrderGetInteger(ORDER_MAGIC) != MagicNumber)
         continue;

      if((ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) == type)
      {
         ticket = id;
         price = OrderGetDouble(ORDER_PRICE_OPEN);
         sl = OrderGetDouble(ORDER_SL);
         return true;
      }
   }

   return false;
}

double MinimumDistance()
{
   int stops = (int)SymbolInfoInteger(
      _Symbol, SYMBOL_TRADE_STOPS_LEVEL);

   int freeze = (int)SymbolInfoInteger(
      _Symbol, SYMBOL_TRADE_FREEZE_LEVEL);

   return MathMax(stops, freeze) * _Point;
}

// Sum PROFIT + SWAP + COMMISSION across all deals of a position
// (entry + exit), so cycle stop / re-arm uses net account PnL.
double PositionDealsNetProfit(ulong positionId)
{
   double net = 0.0;

   if(positionId == 0)
      return net;

   if(!HistorySelectByPosition(positionId))
   {
      datetime to = TimeCurrent() + 1;
      datetime from = to - 86400 * 30;
      if(!HistorySelect(from, to))
         return net;
   }

   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;

      if((ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID) != positionId)
         continue;

      if(HistoryDealGetString(deal, DEAL_SYMBOL) != _Symbol)
         continue;

      net += HistoryDealGetDouble(deal, DEAL_PROFIT);
      net += HistoryDealGetDouble(deal, DEAL_SWAP);
      net += HistoryDealGetDouble(deal, DEAL_COMMISSION);
   }

   return net;
}

// Convert desired monetary SL/TP into price.
bool PriceForMoney(ENUM_ORDER_TYPE orderType,
                   double openPrice,
                   double closeReference,
                   double desiredMoney,
                   double volume,
                   double &resultPrice)
{
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0)
      tick = _Point;

   double p0, p1;

   if(!OrderCalcProfit(orderType, _Symbol, volume,
                       openPrice, closeReference, p0))
      return false;

   double nextPrice =
      (orderType == ORDER_TYPE_BUY)
      ? closeReference + tick
      : closeReference - tick;

   if(!OrderCalcProfit(orderType, _Symbol, volume,
                       openPrice, nextPrice, p1))
      return false;

   double moneyPerTick = p1 - p0;
   if(moneyPerTick <= 0.0)
      return false;

   double ticksNeeded = (desiredMoney - p0) / moneyPerTick;

   resultPrice = NormalizePrice(
      closeReference +
      ((orderType == ORDER_TYPE_BUY) ? 1.0 : -1.0)
      * ticksNeeded * tick
   );

   return true;
}

void PrintInitDiagnostics()
{
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double stepLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   int stops = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   int freeze = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double volume = VolumeForOrder();

   PrintFormat(
      "Diagnostics %s | digits=%d point=%.5f tickSize=%.5f tickValue=%.5f | "
      "stops=%d freeze=%d minDist=%.5f | lot min=%.4f step=%.4f use=%.4f",
      _Symbol, _Digits, _Point, tickSize, tickValue,
      stops, freeze, MinimumDistance(), minLot, stepLot, volume);

   if(volume <= 0.0)
   {
      Print("VolumeForOrder invalid — check LotSize vs broker min/step.");
      return;
   }

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;

   double minDist = MinimumDistance() +
                    SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double distance = MathMax(PendingDistance, minDist);
   double buyPrice = NormalizePrice(tick.ask + distance);
   double buySL = 0.0;

   if(PriceForMoney(ORDER_TYPE_BUY, buyPrice, buyPrice,
                    -InitialSL_USD, volume, buySL))
   {
      PrintFormat(
         "Initial SL sample BUY @ %.5f → SL %.5f (dist %.5f, target -%.2f USD). "
         "Broker minDist %.5f%s",
         buyPrice, buySL, buyPrice - buySL, InitialSL_USD, minDist,
         (buyPrice - buySL < minDist)
            ? " — TOO CLOSE, pendings will not place."
            : " — OK");
   }
   else
   {
      Print("Initial SL PriceForMoney failed on init sample.");
   }

   PrintFormat(
      "PendingDistance=%.5f (raw). On many XAUUSD feeds 15.0 means $15 — confirm intent.",
      PendingDistance);
}

//---------------- CHART DISPLAY (Thunder style) ----------------//
void DeleteDisplayObjects()
{
   int total = ObjectsTotal(0, -1, -1);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, -1, -1);
      if(StringFind(name, OBJ_PREFIX) == 0)
         ObjectDelete(0, name);
   }
}

void UpsertTrend(const string id,
                 const datetime t1,
                 const double p1,
                 const datetime t2,
                 const double p2,
                 const color clr,
                 const ENUM_LINE_STYLE style)
{
   string name = OBJ_PREFIX + id;
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_TREND, 0, t1, p1, t2, p2);
      ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, true);
      ObjectSetInteger(0, name, OBJPROP_RAY_LEFT, false);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, LineWidth);
   }
   else
   {
      ObjectMove(0, name, 0, t1, p1);
      ObjectMove(0, name, 1, t2, p2);
   }

   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, LineWidth);
}

void UpsertLabel(const string id,
                 const datetime t,
                 const double price,
                 const string text,
                 const color clr)
{
   string name = OBJ_PREFIX + id;
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_TEXT, 0, t, price);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
   }
   else
   {
      ObjectMove(0, name, 0, t, price);
   }

   ObjectSetString(0, name, OBJPROP_TEXT, "  " + text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
}

void UpsertArrow(const string id,
                 const datetime t,
                 const double price,
                 const bool isBuy,
                 const color clr)
{
   if(!ShowCandleMarkers)
      return;

   string name = OBJ_PREFIX + id;
   ENUM_OBJECT type = isBuy ? OBJ_ARROW_BUY : OBJ_ARROW_SELL;

   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, type, 0, t, price);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   }
   else
   {
      ObjectMove(0, name, 0, t, price);
   }

   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
}

void HideObject(const string id)
{
   string name = OBJ_PREFIX + id;
   if(ObjectFind(0, name) >= 0)
      ObjectDelete(0, name);
}

void DrawSideLevels(const string side,
                    const datetime t0,
                    const double entry,
                    const double sl,
                    const double tp,
                    const color entryClr,
                    const ENUM_LINE_STYLE style,
                    const bool isBuy)
{
   datetime t1 = t0;
   datetime t2 = t0 + PeriodSeconds() * 8;
   if(t2 <= t1)
      t2 = t1 + 60;

   // Label sits near the right of the visible segment (Thunder-style).
   datetime tLabel = t2;

   UpsertTrend(side + "_ENTRY", t1, entry, t2, entry, entryClr, style);
   UpsertLabel(side + "_ENTRY_L", tLabel, entry,
               StringFormat("%s ENTRY %s", side, DoubleToString(entry, _Digits)),
               entryClr);

   if(sl > 0.0)
   {
      UpsertTrend(side + "_SL", t1, sl, t2, sl, ClrSL, style);
      UpsertLabel(side + "_SL_L", tLabel, sl,
                  StringFormat("%s SL %s", side, DoubleToString(sl, _Digits)),
                  ClrSL);
   }
   else
   {
      HideObject(side + "_SL");
      HideObject(side + "_SL_L");
   }

   if(tp > 0.0)
   {
      UpsertTrend(side + "_TP", t1, tp, t2, tp, ClrTP, style);
      UpsertLabel(side + "_TP_L", tLabel, tp,
                  StringFormat("%s TP %s (vis $%.2f)", side,
                               DoubleToString(tp, _Digits), VisualTP_USD),
                  ClrTP);
   }
   else
   {
      HideObject(side + "_TP");
      HideObject(side + "_TP_L");
   }

   UpsertArrow(side + "_ARR", t0, entry, isBuy, entryClr);
}

void ClearSide(const string side)
{
   HideObject(side + "_ENTRY");
   HideObject(side + "_ENTRY_L");
   HideObject(side + "_SL");
   HideObject(side + "_SL_L");
   HideObject(side + "_TP");
   HideObject(side + "_TP_L");
   HideObject(side + "_ARR");
}

void UpdateStatusComment()
{
   string state = CycleStopped ? "STOPPED (loss)" :
                  (IsOurPosition() ? "IN POSITION" :
                   (PositionSeen ? "FILL SYNC" : "ARMED"));

   Comment(
      "JM GOLD ULTIMATE SCALPER v0.0.2\n",
      "Symbol: ", _Symbol, "\n",
      "State: ", state, "\n",
      "Peak: ", DoubleToString(PeakProfit, 2),
      " | Trail start $", DoubleToString(TrailingStart_USD, 2),
      " | Visual TP $", DoubleToString(VisualTP_USD, 2), "\n",
      "SL/TP lines: ", (ShowLevelsDisplay ? "ON" : "OFF"),
      " (TP is visual only — trailing manages exit)"
   );
}

void UpdateChartDisplay()
{
   UpdateStatusComment();

   if(!ShowLevelsDisplay)
   {
      DeleteDisplayObjects();
      return;
   }

   double volume = VolumeForOrder();
   if(volume <= 0.0)
      volume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   ulong posTicket = OurPositionTicket();
   if(posTicket != 0 && PositionSelectByTicket(posTicket))
   {
      ClearSide("BUY");
      ClearSide("SELL");

      ENUM_POSITION_TYPE ptype =
         (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      datetime t0 = (datetime)PositionGetInteger(POSITION_TIME);
      ENUM_ORDER_TYPE dir =
         (ptype == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;

      double tp = 0.0;
      if(VisualTP_USD > 0.0)
         PriceForMoney(dir, entry, entry, VisualTP_USD, volume, tp);

      string side = (ptype == POSITION_TYPE_BUY) ? "POSBUY" : "POSSELL";
      string other = (ptype == POSITION_TYPE_BUY) ? "POSSELL" : "POSBUY";
      ClearSide(other);
      ClearSide("BUY");
      ClearSide("SELL");

      DrawSideLevels(side, t0, entry, sl, tp, ClrEntry, STYLE_SOLID,
                     ptype == POSITION_TYPE_BUY);
      ChartRedraw(0);
      return;
   }

   ClearSide("POSBUY");
   ClearSide("POSSELL");

   ulong buyTicket, sellTicket;
   double buyPrice, sellPrice, buySL, sellSL;

   bool hasBuy = FindPending(ORDER_TYPE_BUY_STOP, buyTicket, buyPrice, buySL);
   bool hasSell = FindPending(ORDER_TYPE_SELL_STOP, sellTicket, sellPrice, sellSL);

   datetime t0 = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(t0 == 0)
      t0 = TimeCurrent();

   if(hasBuy)
   {
      double tp = 0.0;
      if(VisualTP_USD > 0.0)
         PriceForMoney(ORDER_TYPE_BUY, buyPrice, buyPrice, VisualTP_USD, volume, tp);
      DrawSideLevels("BUY", t0, buyPrice, buySL, tp, ClrPending, STYLE_DASH, true);
   }
   else
      ClearSide("BUY");

   if(hasSell)
   {
      double tp = 0.0;
      if(VisualTP_USD > 0.0)
         PriceForMoney(ORDER_TYPE_SELL, sellPrice, sellPrice, VisualTP_USD, volume, tp);
      DrawSideLevels("SELL", t0, sellPrice, sellSL, tp, ClrPending, STYLE_DASH, false);
   }
   else
      ClearSide("SELL");

   ChartRedraw(0);
}

//---------------- PENDING GRID ----------------//
void MaintainPendingOrders()
{
   if(CycleStopped)
   {
      DeleteOurPending();
      return;
   }

   if(!TradingAllowed())
      return;

   SyncPositionSeen();

   if(IsOurPosition())
   {
      PositionSeen = true;
      DeleteOurPending();
      return;
   }

   // Filled (DEAL_IN) but position not selectable yet — do not re-arm.
   if(PositionSeen)
   {
      DeleteOurPending();
      return;
   }

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;

   if(tick.ask - tick.bid > MaxSpreadPrice)
      return;

   double volume = VolumeForOrder();
   if(volume <= 0.0)
      return;

   double minDist = MinimumDistance() +
                    SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);

   double distance = MathMax(PendingDistance, minDist);

   double buyPrice = NormalizePrice(tick.ask + distance);
   double sellPrice = NormalizePrice(tick.bid - distance);

   ulong buyTicket, sellTicket;
   double oldBuy, oldSell, oldBuySL, oldSellSL;

   bool hasBuy = FindPending(
      ORDER_TYPE_BUY_STOP, buyTicket, oldBuy, oldBuySL);

   bool hasSell = FindPending(
      ORDER_TYPE_SELL_STOP, sellTicket, oldSell, oldSellSL);

   double buySL = 0.0;
   double sellSL = 0.0;

   if(!PriceForMoney(ORDER_TYPE_BUY, buyPrice,
                     buyPrice, -InitialSL_USD,
                     volume, buySL))
      return;

   if(!PriceForMoney(ORDER_TYPE_SELL, sellPrice,
                     sellPrice, -InitialSL_USD,
                     volume, sellSL))
      return;

   // Broker may reject SL closer than minimum distance.
   // Do not silently widen monetary risk.
   if(buyPrice - buySL < minDist ||
      sellSL - sellPrice < minDist)
   {
      Print("Initial SL too close for broker rules.");
      return;
   }

   double tolerance =
      SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);

   if(hasBuy)
   {
      if(MathAbs(oldBuy - buyPrice) >= tolerance)
      {
         if(!trade.OrderModify(buyTicket, buyPrice,
                               buySL, 0.0,
                               ORDER_TIME_GTC, 0))
            Print("Buy modify: ",
                  trade.ResultRetcodeDescription());
      }
   }
   else
   {
      if(!trade.BuyStop(volume, buyPrice, _Symbol,
                        buySL, 0.0, ORDER_TIME_GTC,
                        0, "JM BUY STOP"))
         Print("Buy Stop: ",
               trade.ResultRetcodeDescription());
   }

   if(hasSell)
   {
      if(MathAbs(oldSell - sellPrice) >= tolerance)
      {
         if(!trade.OrderModify(sellTicket, sellPrice,
                               sellSL, 0.0,
                               ORDER_TIME_GTC, 0))
            Print("Sell modify: ",
                  trade.ResultRetcodeDescription());
      }
   }
   else
   {
      if(!trade.SellStop(volume, sellPrice, _Symbol,
                         sellSL, 0.0, ORDER_TIME_GTC,
                         0, "JM SELL STOP"))
         Print("Sell Stop: ",
               trade.ResultRetcodeDescription());
   }
}

//---------------- TRAILING ----------------//
void ManageTrailing()
{
   ulong ticket = OurPositionTicket();
   if(ticket == 0)
   {
      TrackedPosition = 0;
      PeakProfit = 0.0;
      return;
   }

   PositionSeen = true;

   if(!PositionSelectByTicket(ticket))
      return;

   if(ticket != TrackedPosition)
   {
      TrackedPosition = ticket;
      PeakProfit = 0.0;
   }

   ENUM_POSITION_TYPE type =
      (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double volume = PositionGetDouble(POSITION_VOLUME);
   double oldSL = PositionGetDouble(POSITION_SL);
   double currentProfit = PositionGetDouble(POSITION_PROFIT);

   PeakProfit = MathMax(PeakProfit, currentProfit);

   if(PeakProfit < TrailingStart_USD)
      return;

   double targetLock =
      MathMax(TrailingLock_USD,
              PeakProfit - TrailingGap_USD);

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;

   ENUM_ORDER_TYPE direction =
      (type == POSITION_TYPE_BUY)
      ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;

   double closePrice =
      (type == POSITION_TYPE_BUY) ? tick.bid : tick.ask;

   double newSL = 0.0;

   if(!PriceForMoney(direction, openPrice,
                     closePrice, targetLock,
                     volume, newSL))
      return;

   double minDist = MinimumDistance();

   if(type == POSITION_TYPE_BUY)
   {
      if(newSL >= tick.bid - minDist)
         return;

      if(oldSL != 0.0 && newSL <= oldSL)
         return;
   }
   else
   {
      if(newSL <= tick.ask + minDist)
         return;

      if(oldSL != 0.0 && newSL >= oldSL)
         return;
   }

   if(!trade.PositionModify(ticket, newSL, 0.0))
      Print("Trailing modify: ",
            trade.ResultRetcodeDescription());
}

//---------------- TRADE EVENTS ----------------//
void OnTradeTransaction(
   const MqlTradeTransaction &trans,
   const MqlTradeRequest &request,
   const MqlTradeResult &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;

   if(!HistoryDealSelect(trans.deal))
      return;

   if(HistoryDealGetString(trans.deal, DEAL_SYMBOL) != _Symbol)
      return;

   if((ulong)HistoryDealGetInteger(
      trans.deal, DEAL_MAGIC) != MagicNumber)
      return;

   ENUM_DEAL_ENTRY entry =
      (ENUM_DEAL_ENTRY)HistoryDealGetInteger(
         trans.deal, DEAL_ENTRY);

   ulong positionId =
      (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);

   if(entry == DEAL_ENTRY_IN)
   {
      PositionSeen = true;
      PeakProfit = 0.0;
      DeleteOurPending();
      UpdateChartDisplay();
      return;
   }

   if(entry == DEAL_ENTRY_OUT ||
      entry == DEAL_ENTRY_OUT_BY)
   {
      double net = PositionDealsNetProfit(positionId);

      if(net < 0.0)
      {
         CycleStopped = true;
         SaveCycleStopped();
         PrintFormat(
            "Net loss exit (%.2f incl. commission/swap). Cycle stopped. "
            "Set RestartCycle=true to re-arm.",
            net);
      }
      else
      {
         PrintFormat(
            "Net profitable exit (%.2f incl. commission/swap). Re-arming pendings.",
            net);
      }

      PositionSeen = false;
      TrackedPosition = 0;
      PeakProfit = 0.0;
      UpdateChartDisplay();
   }
}

//---------------- EVENTS ----------------//
int OnInit()
{
   if(LotSize <= 0.0 ||
      PendingDistance <= 0.0 ||
      InitialSL_USD <= 0.0 ||
      TrailingStart_USD <= 0.0 ||
      TrailingLock_USD < 0.0 ||
      TrailingGap_USD <= 0.0 ||
      UpdateSeconds < 1 ||
      VisualTP_USD < 0.0)
      return INIT_PARAMETERS_INCORRECT;

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(DeviationPoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   LoadCycleStopped();

   PositionSeen = IsOurPosition();
   TrackedPosition = OurPositionTicket();
   PeakProfit = 0.0;

   EventSetTimer(UpdateSeconds);

   Print("JM GOLD ULTIMATE SCALPER V0.0.2 STARTED");
   PrintFormat("CycleStopped=%s | PositionSeen=%s | RestartCycle=%s | ShowLevels=%s",
               CycleStopped ? "true" : "false",
               PositionSeen ? "true" : "false",
               RestartCycle ? "true" : "false",
               ShowLevelsDisplay ? "true" : "false");
   PrintInitDiagnostics();
   UpdateChartDisplay();

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   SaveCycleStopped();
   DeleteDisplayObjects();
   Comment("");
}

void OnTick()
{
   ManageTrailing();
   UpdateChartDisplay();
}

void OnTimer()
{
   if(RestartCycle && CycleStopped)
   {
      CycleStopped = false;
      SaveCycleStopped();
      Print("RestartCycle: cycle re-armed. Set RestartCycle back to false.");
   }

   SyncPositionSeen();
   ManageTrailing();
   MaintainPendingOrders();
   UpdateChartDisplay();
}
//+------------------------------------------------------------------+
