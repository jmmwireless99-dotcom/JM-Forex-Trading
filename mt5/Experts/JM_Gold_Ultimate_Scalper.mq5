//+------------------------------------------------------------------+
//| JM_Gold_Ultimate_Scalper.mq5                                     |
//| JM GOLD ULTIMATE SCALPER V0.0.2                                  |
//| Dynamic Follow-Price Pending Orders + Profit Trailing           |
//| Platform: MetaTrader 5 (MQL5)                                    |
//+------------------------------------------------------------------+
#property copyright "JM Tech Solution"
#property version   "0.002"
#property description "Gold scalper: follow-price Buy/Sell stops + USD trailing"
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

// No fixed TP.
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
                 double &price)
{
   ticket = 0;
   price = 0.0;

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
      // Fallback: load recent history then filter by position id.
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

// Convert desired monetary SL into price.
// Uses OrderCalcProfit to account for contract specifications.
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
   double oldBuy, oldSell;

   bool hasBuy = FindPending(
      ORDER_TYPE_BUY_STOP, buyTicket, oldBuy);

   bool hasSell = FindPending(
      ORDER_TYPE_SELL_STOP, sellTicket, oldSell);

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
      UpdateSeconds < 1)
      return INIT_PARAMETERS_INCORRECT;

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(DeviationPoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   LoadCycleStopped();

   // Fresh attach: trust live positions only (clears stale PositionSeen after restart).
   PositionSeen = IsOurPosition();
   TrackedPosition = OurPositionTicket();
   PeakProfit = 0.0;

   EventSetTimer(UpdateSeconds);

   Print("JM GOLD ULTIMATE SCALPER V0.0.2 STARTED");
   PrintFormat("CycleStopped=%s | PositionSeen=%s | RestartCycle=%s",
               CycleStopped ? "true" : "false",
               PositionSeen ? "true" : "false",
               RestartCycle ? "true" : "false");
   PrintInitDiagnostics();

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   SaveCycleStopped();
}

void OnTick()
{
   ManageTrailing();
}

void OnTimer()
{
   // Allow toggle RestartCycle without full chart recreate in some builds.
   if(RestartCycle && CycleStopped)
   {
      CycleStopped = false;
      SaveCycleStopped();
      Print("RestartCycle: cycle re-armed. Set RestartCycle back to false.");
   }

   SyncPositionSeen();
   ManageTrailing();
   MaintainPendingOrders();
}
//+------------------------------------------------------------------+
