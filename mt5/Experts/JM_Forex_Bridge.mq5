//+------------------------------------------------------------------+
//| JM_Forex_Bridge.mq5                                              |
//| JM Forex ↔ cloud desk (MT5) — v1.06                              |
//+------------------------------------------------------------------+
#property copyright "JM Forex / JM TECH SOLUTION"
#property link      "https://jmtechsolution.cloud/fx/"
        #property version   "1.06"
#property description "JM Forex MT5 bridge — Common Files CSV + Algo Trading"
#property strict

#include <Trade/Trade.mqh>

input string InpSymbol         = "XAUUSD";   // Chart/symbol (auto-resolves broker suffix)
input long   InpMagic          = 260719;
input int    InpSlippagePoints = 30;
input int    InpPollMs         = 500;
input bool   UseCommonFolder   = true;       // MUST stay true for Windows agent

CTrade trade;
string g_symbol = "";
string g_last_cmd_id = "";

string ResolveSymbol(string wanted)
{
   string w = wanted;
   StringTrimLeft(w);
   StringTrimRight(w);
   if(StringLen(w) == 0)
      w = "XAUUSD";
   if(SymbolSelect(w, true))
      return w;

   // Common broker suffixes for gold
   string suffixes[8] = {".", "m", ".m", "pro", ".pro", "c", ".c", "s"};
   for(int i = 0; i < 8; i++)
   {
      string cand = "XAUUSD" + suffixes[i];
      if(SymbolSelect(cand, true))
         return cand;
   }

   // Fall back to chart symbol if it looks like gold
   string chart_sym = Symbol();
   string upper = chart_sym;
   StringToUpper(upper);
   if(StringFind(upper, "XAU") >= 0 || StringFind(upper, "GOLD") >= 0)
   {
      if(SymbolSelect(chart_sym, true))
         return chart_sym;
   }
   return w;
}

string TradeBlockReason()
{
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
      return "terminal_not_connected";
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      return "AlgoTrading_toolbar_OFF_click_Algo_Trading_green";
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      return "EA_Allow_Algo_Trading_unchecked_reattach_EA";
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
      return "account_trading_disabled_by_broker";
   if(!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      return "account_blocks_Expert_Advisors";
   if(!SymbolInfoInteger(g_symbol, SYMBOL_TRADE_MODE))
      return "symbol_trade_disabled_or_market_closed";
   return "";
}

void UpdateChartComment()
{
   string block = TradeBlockReason();
   string ok = (StringLen(block) == 0) ? "YES" : "NO";
   Comment(
      "JM Forex MT5 Bridge v1.06\n",
      "Symbol: ", g_symbol, "\n",
      "Login: ", IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)), "\n",
      "trade_ok=", ok, "\n",
      (StringLen(block) > 0 ? ("block=" + block + "\n") : ""),
      "Common Files: ", (UseCommonFolder ? "YES" : "NO — set true!"), "\n",
      "Keep RUN_AGENT_MT5.bat open"
   );
}

int OpenBridge(string name, int mode)
{
   int flags = mode | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE;
   if(UseCommonFolder)
      flags = flags | FILE_COMMON;
   return FileOpen(name, flags);
}

void WriteAck(string cmd_id, string result, string detail)
{
   int h = OpenBridge("jm_ack.csv", FILE_WRITE | FILE_REWRITE);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, cmd_id + "," + result + "," + detail + "\n");
   FileClose(h);
}

void WriteStatus()
{
   int h = OpenBridge("jm_status.csv", FILE_WRITE | FILE_REWRITE);
   if(h == INVALID_HANDLE)
      return;
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string block = TradeBlockReason();
   int trade_ok = (StringLen(block) == 0) ? 1 : 0;
   string line = "ok," +
      DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "," +
      DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + "," +
      IntegerToString(PositionsTotal()) + "," +
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "," +
      IntegerToString(login) + "," +
      IntegerToString(trade_ok) + "," +
      block + "\n";
   FileWriteString(h, line);
   FileClose(h);
}

void WriteTicks()
{
   double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
   int h = OpenBridge("jm_ticks.csv", FILE_WRITE | FILE_REWRITE);
   if(h == INVALID_HANDLE)
      return;
   string line = g_symbol + "," +
      DoubleToString(bid, 5) + "," +
      DoubleToString(ask, 5) + "," +
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\n";
   FileWriteString(h, line);
   FileClose(h);
}

void WritePositions()
{
   int h = OpenBridge("jm_positions.csv", FILE_WRITE | FILE_REWRITE);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, "ticket,symbol,side,lots,open_price,sl,tp,profit\n");
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      string pos_sym = PositionGetString(POSITION_SYMBOL);
      if(pos_sym != g_symbol)
         continue;
      long type = PositionGetInteger(POSITION_TYPE);
      string side = (type == POSITION_TYPE_BUY) ? "BUY" : "SELL";
      string line = IntegerToString((long)ticket) + "," +
         pos_sym + "," +
         side + "," +
         DoubleToString(PositionGetDouble(POSITION_VOLUME), 2) + "," +
         DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), 5) + "," +
         DoubleToString(PositionGetDouble(POSITION_SL), 5) + "," +
         DoubleToString(PositionGetDouble(POSITION_TP), 5) + "," +
         DoubleToString(PositionGetDouble(POSITION_PROFIT), 2) + "\n";
      FileWriteString(h, line);
   }
   FileClose(h);
}

bool CloseAllMagic()
{
   bool ok = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;
      if(!trade.PositionClose(ticket))
         ok = false;
   }
   return ok;
}

bool CloseOppositeMagic(string side)
{
   // Close only the opposite side — do not flatten a same-direction position.
   bool ok = true;
   long want_type = (side == "BUY") ? POSITION_TYPE_SELL : POSITION_TYPE_BUY;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;
      if(PositionGetInteger(POSITION_TYPE) != want_type)
         continue;
      if(!trade.PositionClose(ticket))
         ok = false;
   }
   return ok;
}

bool HasSameSideMagic(string side)
{
   long want_type = (side == "BUY") ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;
      if(PositionGetInteger(POSITION_TYPE) == want_type)
         return true;
   }
   return false;
}

void ProcessCommandLine(string line)
{
   string parts[];
   int n = StringSplit(line, ',', parts);
   if(n < 2)
      return;

   string cmd_id = parts[0];
   string action = parts[1];
   if(cmd_id == g_last_cmd_id)
      return;
   g_last_cmd_id = cmd_id;

   if(action == "PING")
   {
      WriteAck(cmd_id, "OK", "pong");
      return;
   }
   if(action == "CLOSE" || action == "CLOSE_ALL")
   {
      bool closed = CloseAllMagic();
      WriteAck(cmd_id, closed ? "OK" : "ERR", closed ? "closed" : IntegerToString(GetLastError()));
      return;
   }
   if(action != "OPEN" || n < 5)
   {
      WriteAck(cmd_id, "ERR", "bad_command");
      return;
   }

   string symbol = parts[2];
   string side = parts[3];
   double lots = StringToDouble(parts[4]);
   double sl = (n > 5 && StringLen(parts[5]) > 0) ? StringToDouble(parts[5]) : 0;
   double tp = (n > 6 && StringLen(parts[6]) > 0) ? StringToDouble(parts[6]) : 0;
   string comment = (n > 7) ? parts[7] : "JM";

   // Accept desk "XAUUSD" even when broker uses a suffix.
   string sym_u = symbol;
   StringToUpper(sym_u);
   string g_u = g_symbol;
   StringToUpper(g_u);
   bool gold_match =
      (symbol == g_symbol) ||
      (StringFind(sym_u, "XAU") >= 0 && StringFind(g_u, "XAU") >= 0) ||
      (StringFind(sym_u, "GOLD") >= 0 && StringFind(g_u, "GOLD") >= 0);

   if(!gold_match || lots <= 0)
   {
      WriteAck(cmd_id, "ERR", "symbol_or_lots");
      return;
   }

   string block = TradeBlockReason();
   if(StringLen(block) > 0)
   {
      WriteAck(cmd_id, "ERR", block);
      return;
   }

   // Already in a same-direction JM trade — do not churn / re-enter.
   if(HasSameSideMagic(side))
   {
      WriteAck(cmd_id, "OK", "already_open_same_side");
      return;
   }

   // Only flatten the opposite side (anti-flip churn on every signal).
   CloseOppositeMagic(side);
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(g_symbol);

   bool sent = false;
   if(side == "BUY")
      sent = trade.Buy(lots, g_symbol, 0, sl, tp, comment);
   else if(side == "SELL")
      sent = trade.Sell(lots, g_symbol, 0, sl, tp, comment);
   else
   {
      WriteAck(cmd_id, "ERR", "bad_side");
      return;
   }
   if(!sent && (sl > 0 || tp > 0) && trade.ResultRetcode() == TRADE_RETCODE_INVALID_STOPS)
   {
      if(side == "BUY")
         sent = trade.Buy(lots, g_symbol, 0, 0, 0, comment);
      else
         sent = trade.Sell(lots, g_symbol, 0, 0, 0, comment);
   }

   if(!sent)
   {
      int err = GetLastError();
      uint rc = trade.ResultRetcode();
      string why = TradeBlockReason();
      if(StringLen(why) == 0)
      {
         if(err == 4752 || rc == 10027)
            why = "AlgoTrading_toolbar_OFF_or_EA_Allow_Algo_Trading";
         else if(rc == 10016)
            why = "invalid_stops";
         else if(rc == 10019 || err == 134)
            why = "not_enough_money";
         else if(rc != 0)
            why = "retcode_" + IntegerToString((int)rc);
         else
            why = "error_" + IntegerToString(err);
      }
      WriteAck(cmd_id, "ERR", why);
   }
   else
      WriteAck(cmd_id, "OK", IntegerToString((int)trade.ResultOrder()));
}

void ReadCommands()
{
   int h = OpenBridge("jm_command.csv", FILE_READ);
   if(h == INVALID_HANDLE)
      return;
   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringLen(line) == 0)
         continue;
      if(StringFind(line, "id,action") == 0)
         continue;
      ProcessCommandLine(line);
   }
   FileClose(h);
}

int OnInit()
{
   g_symbol = ResolveSymbol(InpSymbol);
   if(!SymbolSelect(g_symbol, true))
   {
      Print("JM Forex MT5 Bridge: cannot select symbol ", g_symbol);
      return(INIT_FAILED);
   }

   trade.SetExpertMagicNumber(InpMagic);
   EventSetMillisecondTimer(InpPollMs);
   WriteStatus();
   WriteTicks();
   WritePositions();
   UpdateChartComment();

   string block = TradeBlockReason();
   Print("JM Forex MT5 Bridge v1.06 ready on ", g_symbol,
         " | trade_ok=", (StringLen(block) == 0 ? "YES" : "NO"),
         " | block=", block,
         " | login=", AccountInfoInteger(ACCOUNT_LOGIN),
         " | common=", UseCommonFolder,
         " | term_trade=", TerminalInfoInteger(TERMINAL_TRADE_ALLOWED),
         " | mql_trade=", MQLInfoInteger(MQL_TRADE_ALLOWED),
         " | acct_expert=", AccountInfoInteger(ACCOUNT_TRADE_EXPERT));
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
}

void OnTimer()
{
   ReadCommands();
   WriteTicks();
   WriteStatus();
   WritePositions();
   UpdateChartComment();
}

void OnTick()
{
   WriteTicks();
}
