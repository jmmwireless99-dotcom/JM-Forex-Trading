//+------------------------------------------------------------------+
//| JM_Lab_XAUUSD_EA.mq5                                             |
//| Lab XAUUSD EMA+RSI Trend — matches jmtechsolution.cloud/lab      |
//+------------------------------------------------------------------+
#property copyright "JM Tech Solution"
#property version   "1.00"
#property description "M5 EMA20/50 + RSI14 trend strategy (Lab XAUUSD preset)"
#property strict

#include <Trade/Trade.mqh>

//--- inputs (defaults = Lab /lab/XAUUSD preset)
input string InpSymbol            = "";           // Symbol (blank = chart symbol)
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M5;   // Timeframe
input double InpLots              = 0.03;         // Lot size
input double InpSlPips            = 50.0;         // Stop loss (pips)
input double InpTpPips            = 50.0;         // Take profit (pips)
input int    InpEmaFast           = 20;           // EMA fast period
input int    InpEmaSlow           = 50;           // EMA slow period
input int    InpRsiPeriod         = 14;           // RSI period
input double InpRsiBuyLo          = 36.0;         // RSI buy zone low
input double InpRsiBuyHi          = 55.0;         // RSI buy zone high
input double InpRsiSellLo         = 45.0;         // RSI sell zone low
input double InpRsiSellHi         = 64.0;         // RSI sell zone high
input int    InpMinBarsBetween    = 3;            // Min M5 bars between entries
input int    InpCooldownAfterLoss = 4;            // Cooldown M5 bars after loss
input double InpMaxSpreadPips     = 3.5;          // Max spread (pips) to enter
input double InpPipSize           = 0.01;         // Pip size (gold = 0.01)
input long   InpMagic             = 260809;       // Magic number
input int    InpSlippagePoints    = 30;           // Slippage (points)
input bool   InpAllowBuy          = true;         // Allow BUY
input bool   InpAllowSell         = true;         // Allow SELL
input bool   InpShowPanel         = true;         // Show status panel

CTrade trade;
string   g_symbol;
int      g_ema_fast_handle = INVALID_HANDLE;
int      g_ema_slow_handle = INVALID_HANDLE;
int      g_rsi_handle      = INVALID_HANDLE;
datetime g_last_bar_time   = 0;
datetime g_last_signal_bar = 0;
datetime g_last_loss_bar   = 0;
string   g_last_status     = "Starting…";

//+------------------------------------------------------------------+
int OnInit()
{
   g_symbol = (InpSymbol == "" ? _Symbol : InpSymbol);
   if(!SymbolSelect(g_symbol, true))
   {
      Print("Symbol not found: ", g_symbol);
      return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(g_symbol);

   g_ema_fast_handle = iMA(g_symbol, InpTimeframe, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   g_ema_slow_handle = iMA(g_symbol, InpTimeframe, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   g_rsi_handle      = iRSI(g_symbol, InpTimeframe, InpRsiPeriod, PRICE_CLOSE);

   if(g_ema_fast_handle == INVALID_HANDLE ||
      g_ema_slow_handle == INVALID_HANDLE ||
      g_rsi_handle == INVALID_HANDLE)
   {
      Print("Indicator init failed");
      return INIT_FAILED;
   }

   g_last_status = "Ready — waiting for M5 close";
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_ema_fast_handle != INVALID_HANDLE) IndicatorRelease(g_ema_fast_handle);
   if(g_ema_slow_handle != INVALID_HANDLE) IndicatorRelease(g_ema_slow_handle);
   if(g_rsi_handle != INVALID_HANDLE)      IndicatorRelease(g_rsi_handle);
   Comment("");
}

//+------------------------------------------------------------------+
double SpreadPips()
{
   double ask = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
   if(ask <= 0 || bid <= 0 || InpPipSize <= 0)
      return 999.0;
   return (ask - bid) / InpPipSize;
}

//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) == g_symbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
void CheckRecentLoss()
{
   datetime from = TimeCurrent() - 86400 * 3;
   if(!HistorySelect(from, TimeCurrent()))
      return;

   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      if(HistoryDealGetString(deal, DEAL_SYMBOL) != g_symbol)
         continue;
      if(HistoryDealGetInteger(deal, DEAL_MAGIC) != InpMagic)
         continue;
      if(HistoryDealGetInteger(deal, DEAL_ENTRY) != DEAL_ENTRY_OUT)
         continue;

      double profit = HistoryDealGetDouble(deal, DEAL_PROFIT)
                    + HistoryDealGetDouble(deal, DEAL_SWAP)
                    + HistoryDealGetDouble(deal, DEAL_COMMISSION);
      if(profit >= 0)
         continue;

      datetime close_time = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
      datetime bar_time = iTime(g_symbol, InpTimeframe, 0);
      // Align to bar that was forming when deal closed
      for(int b = 0; b < 500; b++)
      {
         datetime bt = iTime(g_symbol, InpTimeframe, b);
         if(bt <= close_time)
         {
            if(bt > g_last_loss_bar)
               g_last_loss_bar = bt;
            break;
         }
      }
      break;
   }
}

//+------------------------------------------------------------------+
bool CooldownActive(datetime bar_time)
{
   if(g_last_loss_bar == 0 || InpCooldownAfterLoss <= 0)
      return false;
   int bar_sec = PeriodSeconds(InpTimeframe);
   if(bar_sec <= 0)
      bar_sec = 300;
   return (bar_time - g_last_loss_bar) < InpCooldownAfterLoss * bar_sec;
}

//+------------------------------------------------------------------+
bool SpacingActive(datetime bar_time)
{
   if(g_last_signal_bar == 0 || InpMinBarsBetween <= 0)
      return false;
   int bar_sec = PeriodSeconds(InpTimeframe);
   if(bar_sec <= 0)
      bar_sec = 300;
   return (bar_time - g_last_signal_bar) < InpMinBarsBetween * bar_sec;
}

//+------------------------------------------------------------------+
bool ReadIndicators(const int shift, double &ema_fast, double &ema_slow, double &rsi_val)
{
   double buf_fast[1], buf_slow[1], buf_rsi[1];
   if(CopyBuffer(g_ema_fast_handle, 0, shift, 1, buf_fast) != 1) return false;
   if(CopyBuffer(g_ema_slow_handle, 0, shift, 1, buf_slow) != 1) return false;
   if(CopyBuffer(g_rsi_handle, 0, shift, 1, buf_rsi) != 1)       return false;
   ema_fast = buf_fast[0];
   ema_slow = buf_slow[0];
   rsi_val  = buf_rsi[0];
   return (ema_fast > 0 && ema_slow > 0);
}

//+------------------------------------------------------------------+
int EvaluateSignal(double ema_fast, double ema_slow, double rsi_val, string &reason)
{
   bool bullish = ema_fast > ema_slow;
   bool bearish = ema_fast < ema_slow;

   if(bullish && InpAllowBuy && rsi_val >= InpRsiBuyLo && rsi_val <= InpRsiBuyHi)
   {
      reason = StringFormat("EMA%d>%d · RSI %.1f in buy zone", InpEmaFast, InpEmaSlow, rsi_val);
      return 1; // BUY
   }
   if(bearish && InpAllowSell && rsi_val >= InpRsiSellLo && rsi_val <= InpRsiSellHi)
   {
      reason = StringFormat("EMA%d<%d · RSI %.1f in sell zone", InpEmaFast, InpEmaSlow, rsi_val);
      return -1; // SELL
   }

   if(bullish)
      reason = StringFormat("BUY trend but RSI %.1f outside %.0f-%.0f", rsi_val, InpRsiBuyLo, InpRsiBuyHi);
   else if(bearish)
      reason = StringFormat("SELL trend but RSI %.1f outside %.0f-%.0f", rsi_val, InpRsiSellLo, InpRsiSellHi);
   else
      reason = "EMA flat — no trend";
   return 0;
}

//+------------------------------------------------------------------+
bool OpenTrade(const int direction, const string reason)
{
   double ask = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
   double sl_dist = InpSlPips * InpPipSize;
   double tp_dist = InpTpPips * InpPipSize;
   double sl = 0, tp = 0;
   bool ok = false;

   if(direction > 0)
   {
      sl = ask - sl_dist;
      tp = ask + tp_dist;
      ok = trade.Buy(InpLots, g_symbol, ask, sl, tp, reason);
   }
   else
   {
      sl = bid + sl_dist;
      tp = bid - tp_dist;
      ok = trade.Sell(InpLots, g_symbol, bid, sl, tp, reason);
   }

   if(!ok)
   {
      g_last_status = "Order failed: " + IntegerToString(trade.ResultRetcode()) + " " + trade.ResultRetcodeDescription();
      Print(g_last_status);
      return false;
   }

   g_last_signal_bar = iTime(g_symbol, InpTimeframe, 1);
   g_last_status = (direction > 0 ? "BUY" : "SELL") + " opened · " + reason;
   Print(g_last_status);
   return true;
}

//+------------------------------------------------------------------+
void UpdatePanel()
{
   if(!InpShowPanel)
      return;
   double ema_f = 0, ema_s = 0, rsi_v = 0;
   ReadIndicators(1, ema_f, ema_s, rsi_v);
   Comment(
      "JM Lab XAUUSD EA v1.00\n",
      "Symbol: ", g_symbol, " · ", EnumToString(InpTimeframe), "\n",
      "EMA", InpEmaFast, "=", DoubleToString(ema_f, 2),
      " EMA", InpEmaSlow, "=", DoubleToString(ema_s, 2),
      " RSI=", DoubleToString(rsi_v, 1), "\n",
      "Spread: ", DoubleToString(SpreadPips(), 1), " pips (max ", DoubleToString(InpMaxSpreadPips, 1), ")\n",
      "Status: ", g_last_status
   );
}

//+------------------------------------------------------------------+
void OnTick()
{
   UpdatePanel();

   datetime closed_bar = iTime(g_symbol, InpTimeframe, 1);
   if(closed_bar == 0)
      return;

   // Run once per new closed M5 bar (when bar 1 time changes after a new bar opens)
   datetime current_bar0 = iTime(g_symbol, InpTimeframe, 0);
   if(current_bar0 == g_last_bar_time)
      return;
   g_last_bar_time = current_bar0;

   CheckRecentLoss();

   if(HasOpenPosition())
   {
      g_last_status = "Open position — waiting for close";
      return;
   }

   if(CooldownActive(closed_bar))
   {
      g_last_status = "Cooldown after loss";
      return;
   }

   if(SpacingActive(closed_bar))
   {
      g_last_status = StringFormat("Spacing entries (%d M5 bars)", InpMinBarsBetween);
      return;
   }

   double spread = SpreadPips();
   if(spread > InpMaxSpreadPips)
   {
      g_last_status = StringFormat("Spread %.1f p > max %.1f p", spread, InpMaxSpreadPips);
      return;
   }

   // Need enough history (Lab: 55+ bars)
   if(Bars(g_symbol, InpTimeframe) < InpEmaSlow + 10)
   {
      g_last_status = "Warming up indicators";
      return;
   }

   double ema_f = 0, ema_s = 0, rsi_v = 0;
   if(!ReadIndicators(1, ema_f, ema_s, rsi_v))
   {
      g_last_status = "Indicator read failed";
      return;
   }

   string reason = "";
   int signal = EvaluateSignal(ema_f, ema_s, rsi_v, reason);
   if(signal == 0)
   {
      g_last_status = reason;
      return;
   }

   OpenTrade(signal, reason);
}

//+------------------------------------------------------------------+
