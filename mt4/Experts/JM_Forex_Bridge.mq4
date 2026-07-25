//+------------------------------------------------------------------+
//| JM_Forex_Bridge.mq4                                              |
//| JM Forex ↔ cloud desk (MT4) — v1.08                              |
//| Files: jm4_*.csv in Terminal Common\\Files                       |
//| XAUUSD gold scalp desk                                           |
//+------------------------------------------------------------------+
#property strict
#property copyright "JM Forex / JM TECH SOLUTION"
#property link      "https://jmtechsolution.cloud/fx/"
#property version   "1.08"
#property description "JM Forex MT4 bridge — XAUUSD + AutoTrading"

input string InpSymbol           = "XAUUSD";   // XAUUSD / GOLD (auto-resolves broker suffix)
input int    InpMagic            = 260719;
input int    InpSlippagePoints   = 30;
input int    InpPollMs           = 500;
input bool   UseCommonFolder     = true;       // MUST stay true for Windows agent
input string CommandFile         = "jm4_command.csv";
input string StatusFile          = "jm4_status.csv";
input string PositionsFile       = "jm4_positions.csv";
input string HistoryFile         = "jm4_history.csv";
input string TickFile            = "jm4_ticks.csv";
input string AckFile             = "jm4_ack.csv";

string   g_symbol = "";
datetime g_last_cmd_seen = 0;
string   g_last_cmd_id   = "";

bool IsGoldName(string s)
{
   string u = s;
   StringToUpper(u);
   return (StringFind(u, "XAU") >= 0 || StringFind(u, "GOLD") >= 0);
}

string ResolveSymbol(string wanted)
{
   string w = wanted;
   StringTrimLeft(w);
   StringTrimRight(w);
   if(StringLen(w) == 0)
      w = Symbol(); // prefer chart symbol when blank
   if(StringLen(w) == 0)
      w = "XAUUSD";
   if(MarketInfo(w, MODE_BID) > 0 || SymbolSelect(w, true))
      return w;

   string suffixes[10] = {".", "m", ".m", "pro", ".pro", "c", ".c", "s", "#", ".a"};
   string bases[6];
   bases[0] = "XAUUSD";
   bases[1] = "XAUUSDm";
   bases[2] = "GOLD";
   bases[3] = "XAUUSD.";
   bases[4] = "XAUUSD#";
   bases[5] = "XAUUSD.a";
   int nbase = 6;
   for(int b = 0; b < nbase; b++)
   {
      if(MarketInfo(bases[b], MODE_BID) > 0 || SymbolSelect(bases[b], true))
         return bases[b];
      for(int i = 0; i < 10; i++)
      {
         string cand = bases[b] + suffixes[i];
         if(MarketInfo(cand, MODE_BID) > 0 || SymbolSelect(cand, true))
            return cand;
      }
   }

   string chart_sym = Symbol();
   if(IsGoldName(chart_sym))
      return chart_sym;
   return w;
}

bool SymbolMatchesBridge(string cmd_symbol)
{
   if(cmd_symbol == g_symbol) return true;
   string a = cmd_symbol;
   string b = g_symbol;
   StringToUpper(a);
   StringToUpper(b);
   if(IsGoldName(a) && IsGoldName(b)) return true;
   return false;
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

int EffectiveSlippage()
{
   return InpSlippagePoints;
}

void UpdateChartComment()
{
   string block = TradeBlockReason();
   string ok = (StringLen(block) == 0) ? "YES" : "NO";
   Comment(
      "JM Forex MT4 Bridge v1.08\n",
      "Symbol: ", g_symbol, "\n",
      "XAUUSD gold scalp desk\n",
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

void WriteHistory()
{
   // Recent closed JM magic deals — cloud uses broker PnL (not tick guess).
   int h = FileOpenBridge(HistoryFile, FILE_WRITE);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, "ticket,symbol,side,lots,open_price,close_price,sl,tp,profit,close_time\n");
   int written = 0;
   for(int i = OrdersHistoryTotal() - 1; i >= 0 && written < 50; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderMagicNumber() != InpMagic) continue;
      if(OrderSymbol() != g_symbol) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      if(OrderCloseTime() <= 0) continue;
      double pnl = OrderProfit() + OrderSwap() + OrderCommission();
      string line = StringFormat(
         "%d,%s,%s,%.2f,%.5f,%.5f,%.5f,%.5f,%.2f,%s\n",
         OrderTicket(),
         OrderSymbol(),
         SideToCmd(OrderType()),
         OrderLots(),
         OrderOpenPrice(),
         OrderClosePrice(),
         OrderStopLoss(),
         OrderTakeProfit(),
         pnl,
         TimeToString(OrderCloseTime(), TIME_DATE|TIME_SECONDS)
      );
      FileWriteString(h, line);
      written++;
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
      if(!OrderClose(OrderTicket(), OrderLots(), price, EffectiveSlippage(), clrOrange))
         ok = false;
   }
   return ok;
}

bool CloseOppositeMagic(string side)
{
   bool ok = true;
   int want = (side == "BUY") ? OP_SELL : OP_BUY;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() != InpMagic) continue;
      if(OrderSymbol() != g_symbol) continue;
      if(OrderType() != want) continue;
      double price = (want == OP_BUY) ? MarketInfo(g_symbol, MODE_BID)
                                      : MarketInfo(g_symbol, MODE_ASK);
      if(!OrderClose(OrderTicket(), OrderLots(), price, EffectiveSlippage(), clrOrange))
         ok = false;
   }
   return ok;
}

bool HasSameSideMagic(string side)
{
   int want = (side == "BUY") ? OP_BUY : OP_SELL;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() != InpMagic) continue;
      if(OrderSymbol() != g_symbol) continue;
      if(OrderType() == want) return true;
   }
   return false;
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

   if(!SymbolMatchesBridge(symbol))
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

   if(HasSameSideMagic(side))
   {
      WriteAck(cmd_id, "OK", "already_open_same_side");
      return;
   }

   // Only flatten the opposite side (anti-flip churn).
   CloseOppositeMagic(side);

   double price = (cmd == OP_BUY) ? MarketInfo(g_symbol, MODE_ASK)
                                  : MarketInfo(g_symbol, MODE_BID);
   int slip = EffectiveSlippage();
   int ticket = OrderSend(
      g_symbol, cmd, lots, price, slip,
      sl, tp, comment, InpMagic, 0,
      (cmd == OP_BUY) ? clrDodgerBlue : clrTomato
   );
   if(ticket < 0 && GetLastError() == 130 && (sl > 0 || tp > 0))
   {
      ResetLastError();
      ticket = OrderSend(
         g_symbol, cmd, lots, price, slip,
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
   WriteHistory();
   UpdateChartComment();
   string block = TradeBlockReason();
   Print("JM Forex MT4 Bridge v1.08 ready on ", g_symbol,
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
   WriteHistory();
   UpdateChartComment();
}

void OnTick()
{
   WriteTicks();
}
