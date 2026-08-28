//+------------------------------------------------------------------+
//| JM_Forex_Bridge.mq5                                              |
//| File bridge between JM Forex Python AI and MetaTrader 5          |
//| Same CSV protocol as MT4 JM_Forex_Bridge.mq4                     |
//+------------------------------------------------------------------+
#property copyright "JM Forex"
#property version   "1.00"
#property description "JM Forex AI bridge for MT5 — executes Python signals"

#include <Trade/Trade.mqh>

input string InpSymbol         = "XAUUSD";
input long   InpMagic          = 260719;
input int    InpSlippagePoints = 30;
input int    InpPollMs         = 500;
input bool   UseCommonFolder   = true;
input string CommandFile       = "jm_command.csv";
input string StatusFile        = "jm_status.csv";
input string PositionsFile     = "jm_positions.csv";
input string TickFile          = "jm_ticks.csv";
input string AckFile           = "jm_ack.csv";

CTrade trade;
string g_last_cmd_id = "";

int FileOpenBridge(string name, int mode)
{
   int flags = mode | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE;
   if(UseCommonFolder)
      flags |= FILE_COMMON;
   return FileOpen(name, flags);
}

void WriteAck(string cmd_id, string result, string detail)
{
   int h = FileOpenBridge(AckFile, FILE_WRITE | FILE_REWRITE);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, cmd_id + "," + result + "," + detail + "\n");
   FileClose(h);
}

void WriteStatus()
{
   int h = FileOpenBridge(StatusFile, FILE_WRITE | FILE_REWRITE);
   if(h == INVALID_HANDLE) return;
   string line = StringFormat(
      "ok,%.2f,%.2f,%d,%s\n",
      AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoDouble(ACCOUNT_EQUITY),
      PositionsTotal(),
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)
   );
   FileWriteString(h, line);
   FileClose(h);
}

void WriteTicks()
{
   double bid = SymbolInfoDouble(InpSymbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
   int h = FileOpenBridge(TickFile, FILE_WRITE | FILE_REWRITE);
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
   int h = FileOpenBridge(PositionsFile, FILE_WRITE | FILE_REWRITE);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, "ticket,symbol,side,lots,open_price,sl,tp,profit\n");
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL) != InpSymbol) continue;
      long type = PositionGetInteger(POSITION_TYPE);
      string side = (type == POSITION_TYPE_BUY) ? "BUY" : "SELL";
      string line = StringFormat(
         "%I64u,%s,%s,%.2f,%.5f,%.5f,%.5f,%.2f\n",
         ticket,
         PositionGetString(POSITION_SYMBOL),
         side,
         PositionGetDouble(POSITION_VOLUME),
         PositionGetDouble(POSITION_PRICE_OPEN),
         PositionGetDouble(POSITION_SL),
         PositionGetDouble(POSITION_TP),
         PositionGetDouble(POSITION_PROFIT)
      );
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
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL) != InpSymbol) continue;
      if(!trade.PositionClose(ticket))
         ok = false;
   }
   return ok;
}

void ProcessCommandLine(string line)
{
   string parts[];
   int n = StringSplit(line, ',', parts);
   if(n < 2) return;

   string cmd_id = parts[0];
   string action = parts[1];
   if(cmd_id == g_last_cmd_id) return;
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

   if(symbol != InpSymbol || lots <= 0)
   {
      WriteAck(cmd_id, "ERR", "symbol_or_lots");
      return;
   }

   CloseAllMagic();
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);

   bool sent = false;
   if(side == "BUY")
      sent = trade.Buy(lots, symbol, 0, sl, tp, comment);
   else if(side == "SELL")
      sent = trade.Sell(lots, symbol, 0, sl, tp, comment);
   else
   {
      WriteAck(cmd_id, "ERR", "bad_side");
      return;
   }

   if(!sent)
      WriteAck(cmd_id, "ERR", IntegerToString(GetLastError()));
   else
      WriteAck(cmd_id, "OK", IntegerToString((int)trade.ResultOrder()));
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
      if(StringFind(line, "id,action") == 0) continue;
      ProcessCommandLine(line);
   }
   FileClose(h);
}

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   EventSetMillisecondTimer(InpPollMs);
   WriteStatus();
   WriteTicks();
   WritePositions();
   Print("JM Forex MT5 Bridge ready on ", InpSymbol);
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
