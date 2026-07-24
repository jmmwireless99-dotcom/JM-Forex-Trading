//+------------------------------------------------------------------+
//| JM_Forex_Bridge.mq4                                              |
//| File bridge between JM Forex Python AI and MetaTrader 4          |
//|                                                                  |
//| Install: copy to <MT4>/MQL4/Experts/ then Compile in MetaEditor  |
//| Attach to XAUUSD chart, enable AutoTrading                       |
//| Shared files live in: Terminal -> File -> Open Data Folder       |
//|   -> MQL4/Files/  (or Common/Files when UseCommonFolder=true)    |
//+------------------------------------------------------------------+
#property strict
#property version   "1.02"
#property description "JM Forex AI bridge — executes Python signals on MT4 (remote agent OK)"

input string InpSymbol           = "XAUUSD";
input int    InpMagic            = 260719;
input int    InpSlippagePoints   = 30;
input int    InpPollMs           = 500;
input bool   UseCommonFolder     = true;   // true = Terminal Common\\Files
input string CommandFile         = "jm4_command.csv";
input string StatusFile          = "jm4_status.csv";
input string PositionsFile       = "jm4_positions.csv";
input string TickFile            = "jm4_ticks.csv";
input string AckFile             = "jm4_ack.csv";

datetime g_last_cmd_seen = 0;
string   g_last_cmd_id   = "";

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
   // Match MT5 bridge CSV: ok,balance,equity,positions,time,login
   string line = StringFormat(
      "ok,%.2f,%.2f,%d,%s,%d\n",
      AccountBalance(),
      AccountEquity(),
      OrdersTotal(),
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
      AccountNumber()
   );
   FileWriteString(h, line);
   FileClose(h);
}

void WriteTicks()
{
   double bid = MarketInfo(InpSymbol, MODE_BID);
   double ask = MarketInfo(InpSymbol, MODE_ASK);
   int h = FileOpenBridge(TickFile, FILE_WRITE);
   if(h == INVALID_HANDLE) return;
   string line = StringFormat(
      "%s,%.5f,%.5f,%s\n",
      InpSymbol, bid, ask,
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
      if(OrderSymbol() != InpSymbol) continue;
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
      if(OrderSymbol() != InpSymbol) continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      double price = (type == OP_BUY) ? MarketInfo(InpSymbol, MODE_BID)
                                      : MarketInfo(InpSymbol, MODE_ASK);
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

   if(symbol != InpSymbol)
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

   // One position policy — close opposite/same before new open
   CloseAllMagic();

   double price = (cmd == OP_BUY) ? MarketInfo(symbol, MODE_ASK)
                                  : MarketInfo(symbol, MODE_BID);
   int ticket = OrderSend(
      symbol, cmd, lots, price, InpSlippagePoints,
      sl, tp, comment, InpMagic, 0,
      (cmd == OP_BUY) ? clrDodgerBlue : clrTomato
   );

   if(ticket < 0)
   {
      int err = GetLastError();
      string why = "trade_fail";
      if(err == 4109)
         why = "AutoTrading_OFF_enable_toolbar_and_EA_Allow_live_trading";
      else if(err == 130)
         why = "invalid_stops";
      else if(err == 134)
         why = "not_enough_money";
      else if(err == 136)
         why = "off_quotes";
      else
         why = "error_" + IntegerToString(err);
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
   EventSetMillisecondTimer(InpPollMs);
   WriteStatus();
   WriteTicks();
   WritePositions();
   Print("JM Forex Bridge ready on ", InpSymbol,
         " | folder=", UseCommonFolder ? "COMMON" : "TERMINAL");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   ReadCommands();
   WriteTicks();
   WriteStatus();
   WritePositions();
}

void OnTick()
{
   WriteTicks();
}
