//+------------------------------------------------------------------+
//| JM_Forex_Bridge.mq4                                              |
//| File bridge + optional direct cloud HTTP (no PC agent)            |
//+------------------------------------------------------------------+
#property strict
#property version   "2.00"
#property description "JM Forex AI bridge — local files or direct cloud sync (MT4 real)"

input string InpSymbol           = "GOLD";
input int    InpMagic            = 260719;
input int    InpSlippagePoints   = 30;
input int    InpPollMs           = 200;
input bool   UseCommonFolder     = true;
input string CommandFile         = "jm_command.csv";
input string StatusFile          = "jm_status.csv";
input string PositionsFile       = "jm_positions.csv";
input string TickFile            = "jm_ticks.csv";
input string AckFile             = "jm_ack.csv";

// Direct cloud — no PC agent (JM FX cloud + MT4 real on your PC)
input bool   InpUseCloudBridge   = true;
input string InpApiUrl           = "https://jmtechsolution.cloud/fx/api";
input string InpBridgeToken      = "gTXmD7O-194jS9gveB1I5c9qjmNdqdUv";
input int    InpSyncEveryMs      = 500;

string g_last_cmd_id = "";
string g_ack_line  = "";
uint   g_last_sync_ms = 0;
bool   g_cloud_ready = false;

int FileOpenBridge(string name, int mode)
{
   int flags = mode;
   if(UseCommonFolder)
      flags |= FILE_COMMON;
   return FileOpen(name, flags | FILE_TXT | FILE_ANSI);
}

string JsonEscape(string s)
{
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, "\"", "\\\"");
   StringReplace(s, "\r", "");
   StringReplace(s, "\n", "\\n");
   return s;
}

string ExtractJsonString(string json, string key)
{
   string needle = "\"" + key + "\":\"";
   int pos = StringFind(json, needle);
   if(pos < 0)
      return "";
   pos += StringLen(needle);
   string out = "";
   int len = StringLen(json);
   for(int i = pos; i < len; i++)
   {
      ushort ch = StringGetCharacter(json, i);
      if(ch == '\\' && i + 1 < len)
      {
         ushort nxt = StringGetCharacter(json, i + 1);
         if(nxt == 'n') { out += "\n"; i++; continue; }
         if(nxt == 'r') { i++; continue; }
         if(nxt == 't') { out += "\t"; i++; continue; }
         if(nxt == '"') { out += "\""; i++; continue; }
         if(nxt == '\\') { out += "\\"; i++; continue; }
      }
      if(ch == '"')
         break;
      out += ShortToString((short)ch);
   }
   return out;
}

bool HttpRequest(const string method, const string url, const string body, string &response, int timeout_ms = 8000)
{
   char data[];
   char result[];
   string result_headers;
   string headers = "Content-Type: application/json\r\n";

   if(StringLen(body) > 0)
   {
      StringToCharArray(body, data, 0, WHOLE_ARRAY);
      if(ArraySize(data) > 0)
         ArrayResize(data, ArraySize(data) - 1);
   }

   ResetLastError();
   int code = WebRequest(method, url, headers, timeout_ms, data, result, result_headers);
   if(code == -1)
   {
      int err = GetLastError();
      if(err == 4060)
         Print("JM Bridge: allow WebRequest for ", InpApiUrl, " in MT4 Options -> Expert Advisors");
      else
         Print("JM Bridge HTTP error ", err, " ", method, " ", url);
      return false;
   }
   response = CharArrayToString(result, 0, WHOLE_ARRAY);
   if(code < 200 || code >= 300)
   {
      Print("JM Bridge HTTP ", code, " ", method, " ", url, " -> ", StringSubstr(response, 0, 120));
      return false;
   }
   return true;
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

string BuildStatusCsv()
{
   return StringFormat(
      "ok,%.2f,%.2f,%d,%s\n",
      AccountBalance(),
      AccountEquity(),
      OrdersTotal(),
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)
   );
}

string BuildTicksCsv()
{
   double bid = MarketInfo(InpSymbol, MODE_BID);
   double ask = MarketInfo(InpSymbol, MODE_ASK);
   return StringFormat(
      "%s,%.5f,%.5f,%s\n",
      InpSymbol, bid, ask,
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)
   );
}

string BuildPositionsCsv()
{
   string csv = "ticket,symbol,side,lots,open_price,sl,tp,profit\n";
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() != InpMagic) continue;
      if(OrderSymbol() != InpSymbol) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      csv += StringFormat(
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
   }
   return csv;
}

void WriteAck(string cmd_id, string result, string detail)
{
   g_ack_line = cmd_id + "," + result + "," + detail + "\n";
   int h = FileOpenBridge(AckFile, FILE_WRITE);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, g_ack_line);
   FileClose(h);
}

void WriteStatus()
{
   int h = FileOpenBridge(StatusFile, FILE_WRITE);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, BuildStatusCsv());
   FileClose(h);
}

void WriteTicks()
{
   int h = FileOpenBridge(TickFile, FILE_WRITE);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, BuildTicksCsv());
   FileClose(h);
}

void WritePositions()
{
   int h = FileOpenBridge(PositionsFile, FILE_WRITE);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, BuildPositionsCsv());
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

   string symbol  = parts[2];
   string side    = parts[3];
   double lots    = StringToDouble(parts[4]);
   double sl      = (n > 5 && StringLen(parts[5]) > 0) ? StringToDouble(parts[5]) : 0;
   double tp      = (n > 6 && StringLen(parts[6]) > 0) ? StringToDouble(parts[6]) : 0;
   string comment = (n > 7) ? parts[7] : "JM";

   string trade_symbol = symbol;
   double bid_cmd = MarketInfo(symbol, MODE_BID);
   double bid_inp = MarketInfo(InpSymbol, MODE_BID);
   if(bid_cmd <= 0 && bid_inp > 0)
      trade_symbol = InpSymbol;
   else if(bid_cmd <= 0)
   {
      WriteAck(cmd_id, "ERR", "symbol_or_lots");
      return;
   }

   int cmd = CmdToSide(side);
   if(cmd < 0 || lots <= 0)
   {
      WriteAck(cmd_id, "ERR", "bad_side_or_lots");
      return;
   }

   CloseAllMagic();
   double price = (cmd == OP_BUY) ? MarketInfo(trade_symbol, MODE_ASK)
                                  : MarketInfo(trade_symbol, MODE_BID);
   int ticket = OrderSend(
      trade_symbol, cmd, lots, price, InpSlippagePoints,
      sl, tp, comment, InpMagic, 0,
      (cmd == OP_BUY) ? clrDodgerBlue : clrTomato
   );

   if(ticket < 0)
      WriteAck(cmd_id, "ERR", IntegerToString(GetLastError()));
   else
      WriteAck(cmd_id, "OK", IntegerToString(ticket));
}

void ProcessCommandCsv(string command_csv)
{
   string lines[];
   int count = StringSplit(command_csv, '\n', lines);
   for(int i = 0; i < count; i++)
   {
      string line = lines[i];
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringLen(line) == 0) continue;
      if(StringFind(line, "id,action") == 0) continue;
      ProcessCommandLine(line);
   }
}

void ReadCommandsFromFile()
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

bool CloudSync()
{
   if(StringLen(InpBridgeToken) < 8)
      return false;

   string body = "{\"token\":\"" + JsonEscape(InpBridgeToken) + "\"";
   body += ",\"status\":\"" + JsonEscape(BuildStatusCsv()) + "\"";
   body += ",\"ticks\":\"" + JsonEscape(BuildTicksCsv()) + "\"";
   body += ",\"positions\":\"" + JsonEscape(BuildPositionsCsv()) + "\"";
   if(StringLen(g_ack_line) > 0)
      body += ",\"ack\":\"" + JsonEscape(g_ack_line) + "\"";
   body += "}";

   string url = InpApiUrl + "/mt4/remote/sync";
   string response = "";
   if(!HttpRequest("POST", url, body, response))
      return false;
   g_cloud_ready = (StringFind(response, "\"ok\":true") >= 0 || StringFind(response, "\"ok\": true") >= 0);
   return g_cloud_ready;
}

bool CloudFetchCommand()
{
   if(StringLen(InpBridgeToken) < 8)
      return false;

   string url = InpApiUrl + "/mt4/remote/command?token=" + InpBridgeToken;
   string response = "";
   if(!HttpRequest("GET", url, "", response))
      return false;

   string command = ExtractJsonString(response, "command");
   StringTrimLeft(command);
   StringTrimRight(command);
   if(StringLen(command) == 0)
      return true;

   string before = g_last_cmd_id;
   ProcessCommandCsv(command);
   if(g_last_cmd_id != before)
      CloudSync();
   return true;
}

int OnInit()
{
   EventSetMillisecondTimer(InpPollMs);
   WriteStatus();
   WriteTicks();
   WritePositions();

   if(InpUseCloudBridge)
   {
      Print("JM Forex MT4 Bridge v2 — CLOUD mode (no PC agent)");
      Print("  API: ", InpApiUrl);
      Print("  Allow WebRequest for: ", InpApiUrl, " in MT4 Options -> Expert Advisors");
      CloudSync();
   }
   else
      Print("JM Forex MT4 Bridge v2 — LOCAL file mode on ", InpSymbol);

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   WriteTicks();

   if(InpUseCloudBridge)
   {
      CloudFetchCommand();
      uint now = GetTickCount();
      if(g_last_sync_ms == 0 || (now - g_last_sync_ms) >= (uint)InpSyncEveryMs)
      {
         CloudSync();
         g_last_sync_ms = now;
      }
      return;
   }

   ReadCommandsFromFile();
   WriteStatus();
   WritePositions();
}

void OnTick()
{
   WriteTicks();
}
