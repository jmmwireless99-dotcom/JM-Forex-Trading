//+------------------------------------------------------------------+
//| JM_Forex_Bridge.mq4                                              |
//| JM Forex ↔ cloud desk (MT4) — v1.05                              |
//| Files: jm4_*.csv in Terminal Common\\Files                       |
//+------------------------------------------------------------------+
#property strict
#property copyright "JM Forex / JM TECH SOLUTION"
#property link      "https://jmtechsolution.cloud/fx/"
#property version   "1.05"
#property description "JM Forex MT4 bridge — Common Files CSV + AutoTrading"

input string InpSymbol           = "XAUUSD";   // Chart/symbol (auto-resolves broker suffix)
input int    InpMagic            = 260719;
input int    InpSlippagePoints   = 30;
input int    InpPollMs           = 500;
input bool   UseCommonFolder     = true;       // MUST stay true for Windows agent
input string CommandFile         = "jm4_command.csv";
input string StatusFile          = "jm4_status.csv";
input string PositionsFile       = "jm4_positions.csv";
input string TickFile            = "jm4_ticks.csv";
input string AckFile             = "jm4_ack.csv";

string   g_symbol = "";
datetime g_last_cmd_seen = 0;
string   g_last_cmd_id   = "";

string ResolveSymbol(string wanted)
{
   string w = wanted;
   StringTrimLeft(w);
   StringTrimRight(w);
   if(StringLen(w) == 0)
      w = "XAUUSD";
   if(MarketInfo(w, MODE_BID) > 0 || SymbolSelect(w, true))
      return w;

   string suffixes[8] = {".", "m", ".m", "pro", ".pro", "c", ".c", "s"};
   for(int i = 0; i < 8; i++)
   {
      string cand = "XAUUSD" + suffixes[i];
      if(MarketInfo(cand, MODE_BID) > 0 || SymbolSelect(cand, true))
         return cand;
   }

   string chart_sym = Symbol();
   string upper = chart_sym;
   StringToUpper(upper);
   if(StringFind(upper, "XAU") >= 0 || StringFind(upper, "GOLD") >= 0)
      return chart_sym;
   return w;
}

string TradeBlockReason()
{
   // Precise why OrderSend would return 4109 even when UI "looks" enabled.
   if(!IsConnected())
      return "terminal_not_connected";
   if(!IsExpertEnabled())
      return "AutoTrading_toolbar_OFF_click_AutoTrading_green";
   if(!IsTradeAllowed())
      return "trade_not_allowed_check_EA_Allow_live_trading_and_account";
   if(!IsTradeAllowed(g_symbol, TimeCurrent()))
      return "symbol_trade_disabled_or_market_closed";
   return "";
}

void UpdateChartComment()
{
   string block = TradeBlockReason();
   string ok = (StringLen(block) == 0) ? "YES" : "NO";
   Comment(
      "JM Forex MT4 Bridge v1.05\n",
      "Symbol: ", g_symbol, "\n",
      "Login: ", IntegerToString(AccountNumber()), "\n",
      "trade_ok=", ok, "\n",
      (StringLen(block) > 0 ? ("block=" + block + "\n") : ""),
      "Common Files: ", (UseCommonFolder ? "YES" : "NO — set true!"), "\n",
      "Keep RUN_AGENT_MT4.bat open"
   );
}

int FileOpenBridge(string name, int mode)
{
   int flags = mode;
   if(UseCommonFolder)
      flags |= FILE_COMMON;
   return FileOpen(name, flags | FILE_TXT | FILE_ANSI);
}

string SideToCmd(int type)
{
   if(type == OP_BUY) return "BUY";
   if(type == OP_SELL) return "SELL";
   return "UNKNOWN";
}

int CmdToSide(string side)
{
   if(side == "BUY") return OP_BUY;
   if(side == "SELL") return OP_SELL;
   return -1;
}

void WriteAck(string cmd_id, string result, string detail)
{
   int h = FileOpenBridge(AckFile, FILE_WRITE);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, cmd_id + "," + result + "," + detail + "\n");
   FileClose(h);
}

void WriteStatus()
{
   int h = FileOpenBridge(StatusFile, FILE_WRITE);
   if(h == INVALID_HANDLE) return;
   string block = TradeBlockReason();
   int trade_ok = (StringLen(block) == 0) ? 1 : 0;
   // ok,balance,equity,positions,time,login,trade_ok,block
   string line = StringFormat(
      "ok,%.2f,%.2f,%d,%s,%d,%d,%s\n",
      AccountBalance(),
      AccountEquity(),
      OrdersTotal(),
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
      AccountNumber(),
      trade_ok,
      block
   );
   FileWriteString(h, line);
   FileClose(h);
}

void WriteTicks()
{
   double bid = MarketInfo(g_symbol, MODE_BID);
   double ask = MarketInfo(g_symbol, MODE_ASK);
   int h = FileOpenBridge(TickFile, FILE_WRITE);
   if(h == INVALID_HANDLE) return;
   string line = StringFormat(
      "%s,%.5f,%.5f,%s\n",
      g_symbol, bid, ask,
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)
   );
   FileWriteString(h, line);
   FileClose(h);
}

void WritePositions()
{
   int h = FileOpenBridge(PositionsFile, FILE_WRITE);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, "ticket,symbol,side,lots,open_price,sl,tp,profit\n");
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() != InpMagic) continue;
      if(OrderSymbol() != g_symbol) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      string line = StringFormat(
         "%d,%s,%s,%.2f,%.5f,%.5f,%.5f,%.2f\n",
         OrderTicket(),
         OrderSymbol(),
         SideToCmd(OrderType()),
         OrderLots(),
         OrderOpenPrice(),
         OrderStopLoss(),
         OrderTakeProfit(),
         OrderProfit() + OrderSwap() + OrderCommission()
      );
      FileWriteString(h, line);
   }
   FileClose(h);
}

bool CloseAllMagic()
{
   bool ok = true;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() != InpMagic) continue;
      if(OrderSymbol() != g_symbol) continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      double price = (type == OP_BUY) ? MarketInfo(g_symbol, MODE_BID)
                                      : MarketInfo(g_symbol, MODE_ASK);
      if(!OrderClose(OrderTicket(), OrderLots(), price, InpSlippagePoints, clrOrange))
         ok = false;
   }
   return ok;
}

void ProcessCommandLine(string line)
{
   // id,action,symbol,side,lots,sl,tp,comment
   string parts[];
   int n = StringSplit(line, ',', parts);
   if(n < 2) return;

   string cmd_id = parts[0];
   string action = parts[1];
   if(cmd_id == g_last_cmd_id) return; // already handled
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

   if(action != "OPEN")
   {
      WriteAck(cmd_id, "ERR", "unknown_action");
      return;
   }

   if(n < 5)
   {
      WriteAck(cmd_id, "ERR", "bad_open_args");
      return;
   }

   string symbol  = parts[2];
   string side    = parts[3];
   double lots    = StringToDouble(parts[4]);
   double sl      = (n > 5 && StringLen(parts[5]) > 0) ? StringToDouble(parts[5]) : 0;
   double tp      = (n > 6 && StringLen(parts[6]) > 0) ? StringToDouble(parts[6]) : 0;
   string comment = (n > 7) ? parts[7] : "JM";

   string sym_u = symbol;
   StringToUpper(sym_u);
   string g_u = g_symbol;
   StringToUpper(g_u);
   bool gold_match =
      (symbol == g_symbol) ||
      (StringFind(sym_u, "XAU") >= 0 && StringFind(g_u, "XAU") >= 0) ||
      (StringFind(sym_u, "GOLD") >= 0 && StringFind(g_u, "GOLD") >= 0);

   if(!gold_match)
   {
      WriteAck(cmd_id, "ERR", "symbol_mismatch");
      return;
   }

   int cmd = CmdToSide(side);
   if(cmd < 0 || lots <= 0)
   {
      WriteAck(cmd_id, "ERR", "bad_side_or_lots");
      return;
   }

   string block = TradeBlockReason();
   if(StringLen(block) > 0)
   {
      WriteAck(cmd_id, "ERR", block);
      return;
   }

   // One position policy — close opposite/same before new open
   CloseAllMagic();

   double price = (cmd == OP_BUY) ? MarketInfo(g_symbol, MODE_ASK)
                                  : MarketInfo(g_symbol, MODE_BID);
   int ticket = OrderSend(
      g_symbol, cmd, lots, price, InpSlippagePoints,
      sl, tp, comment, InpMagic, 0,
      (cmd == OP_BUY) ? clrDodgerBlue : clrTomato
   );
   if(ticket < 0 && GetLastError() == 130 && (sl > 0 || tp > 0))
   {
      ResetLastError();
      ticket = OrderSend(
         g_symbol, cmd, lots, price, InpSlippagePoints,
         0, 0, comment, InpMagic, 0,
         (cmd == OP_BUY) ? clrDodgerBlue : clrTomato
      );
   }

   if(ticket < 0)
   {
      int err = GetLastError();
      string why = TradeBlockReason();
      if(StringLen(why) == 0)
      {
         if(err == 4109)
            why = "AutoTrading_toolbar_OFF_or_EA_Allow_live_trading";
         else if(err == 130)
            why = "invalid_stops";
         else if(err == 134)
            why = "not_enough_money";
         else if(err == 136)
            why = "off_quotes";
         else if(err == 146)
            why = "trade_context_busy_retry";
         else
            why = "error_" + IntegerToString(err);
      }
      WriteAck(cmd_id, "ERR", why);
   }
   else
      WriteAck(cmd_id, "OK", IntegerToString(ticket));
}

void ReadCommands()
{
   int h = FileOpenBridge(CommandFile, FILE_READ);
   if(h == INVALID_HANDLE) return;
   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringLen(line) == 0) continue;
      if(StringFind(line, "id,action") == 0) continue; // header
      ProcessCommandLine(line);
   }
   FileClose(h);
}

int OnInit()
{
   g_symbol = ResolveSymbol(InpSymbol);
   if(MarketInfo(g_symbol, MODE_BID) <= 0)
      SymbolSelect(g_symbol, true);

   EventSetMillisecondTimer(InpPollMs);
   WriteStatus();
   WriteTicks();
   WritePositions();
   UpdateChartComment();
   string block = TradeBlockReason();
   Print("JM Forex MT4 Bridge v1.05 ready on ", g_symbol,
         " | folder=", UseCommonFolder ? "COMMON" : "TERMINAL",
         " | trade_ok=", (StringLen(block) == 0 ? "YES" : "NO"),
         " | block=", block,
         " | login=", AccountNumber(),
         " | expert=", IsExpertEnabled(),
         " | tradeAllowed=", IsTradeAllowed());
   return INIT_SUCCEEDED;
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
