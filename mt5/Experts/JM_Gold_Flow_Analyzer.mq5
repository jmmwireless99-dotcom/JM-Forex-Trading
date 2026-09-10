//+------------------------------------------------------------------+
//| JM_Gold_Flow_Analyzer.mq5                                        |
//| New gold scalper + on-chart analyzer (OK / WEAK / MALI)          |
//| Attach to GOLD# M5. Compile in MetaEditor (F7).                  |
//+------------------------------------------------------------------+
#property copyright "JM Forex"
#property version   "1.00"
#property description "Gold small-candle flow scalper with entry analyzer. Shows OK / WEAK / MALI before any order."
#property strict

#include <Trade/Trade.mqh>

enum ENUM_JM_TRADE_MODE
  {
   MODE_ANALYZER_ONLY = 0,  // Show panel only — no orders
   MODE_BLOCK_MALI    = 1,  // Trade OK + WEAK, skip MALI
   MODE_OK_ONLY       = 2   // Trade OK only
  };

input group "=== Trade ==="
input string             InpSymbol          = "GOLD#";
input double             InpLots            = 0.01;
input long               InpMagic           = 26091070;
input string             InpMasterBuildTag  = "V6.2-A-ANALYZER";
input ENUM_JM_TRADE_MODE InpTradeMode       = MODE_BLOCK_MALI;
input double             InpSLPrice         = 4.0;   // stop distance in price ($)
input double             InpTPPrice         = 5.0;   // take-profit distance (TP5)
input int                InpSlippagePoints  = 40;
input bool               InpAllowBuy        = true;
input bool               InpAllowSell       = true;

input group "=== M5 trend ==="
input int                InpM5FastEMA       = 20;
input int                InpM5SlowEMA       = 50;
input int                InpM5ADXPeriod     = 14;
input double             InpADXMin          = 16.0;  // light — preserve frequency

input group "=== M1 flow ==="
input int                InpM1FastEMA       = 9;
input int                InpM1SlowEMA       = 21;
input int                InpM1RSIPeriod     = 14;
input int                InpM1ATRPeriod     = 14;
input bool               InpRequireM1Flow   = true;

input group "=== Small candle ==="
input double             InpRangeAtr        = 0.7;   // last M1/M5 range <= 70% ATR
input double             InpBodyMax         = 0.45;  // small body / indecision
input double             InpBreakoutAtr     = 0.05;  // breakout buffer beyond small candle
input double             InpNoiseReject     = 0.15;  // reject ultra-tiny candles
input double             InpWideSmall       = 0.8;   // allow slightly wider small candles

input group "=== Filters ==="
input bool               InpUseChopFilter   = true;
input double             InpChopGapPct      = 0.06;  // toxic only with weak ADX
input double             InpWeakADXLevel    = 20.0;
input bool               InpUseFlowScore    = true;
input int                InpBaseScore       = 3;
input int                InpEasierHour      = -1;
input int                InpWeakHourAdd     = 1;
input int                InpWorstHourAdd    = 2;
input bool               InpUseHourRoute    = true;

input group "=== Analyzer panel ==="
input bool               InpShowPanel       = true;
input int                InpPanelX          = 12;
input int                InpPanelY          = 28;

CTrade trade;

int g_m5_fast = INVALID_HANDLE;
int g_m5_slow = INVALID_HANDLE;
int g_m5_adx  = INVALID_HANDLE;
int g_m5_rsi  = INVALID_HANDLE;
int g_m5_atr  = INVALID_HANDLE;
int g_m1_fast = INVALID_HANDLE;
int g_m1_slow = INVALID_HANDLE;

datetime g_last_bar = 0;
string   g_last_action = "waiting for M5 close";
string   g_pfx = "JMFA_";

#define V_OK   0
#define V_WEAK 1
#define V_MALI 2
#define V_WAIT 3

string VerdictName(int v)
  {
   if(v==V_OK)   return "OK";
   if(v==V_WEAK) return "WEAK";
   if(v==V_MALI) return "MALI";
   return "WAIT";
  }

color VerdictColor(int v)
  {
   if(v==V_OK)   return clrLime;
   if(v==V_WEAK) return clrGold;
   if(v==V_MALI) return clrTomato;
   return clrSilver;
  }

string HourBias(int hour)
  {
   if(!InpUseHourRoute) return "NEUTRAL";
   if(hour==21 || hour==22 || hour==23) return "WORST";
   if(hour>=16 && hour<=19) return "BUY";
   if(hour>=0 && hour<=13)  return "SELL";
   return "NEUTRAL";
  }

int RequiredScore(const string side, const string bias)
  {
   int need = InpBaseScore;
   if(bias=="WORST")
      need += InpWorstHourAdd;
   else if(bias=="NEUTRAL")
      need += InpWeakHourAdd;
   else if(bias==side)
      need += InpEasierHour;
   else
      need += InpWorstHourAdd;
   if(need<1) need=1;
   if(need>6) need=6;
   return need;
  }

bool Copy1(int handle, int buf, int shift, double &out)
  {
   double v[];
   ArraySetAsSeries(v, true);
   if(CopyBuffer(handle, buf, shift, 1, v)<1)
      return false;
   out = v[0];
   return true;
  }

struct SideResult
  {
   string side;
   int    verdict;
   int    score;
   int    required;
   string reasons;
  };

struct ScanResult
  {
   int    overall;
   string preferred;
   int    hour;
   string bias;
   double adx;
   double rsi;
   double ema_fast;
   double ema_slow;
   double atr;
   string summary;
   SideResult buy;
   SideResult sell;
  };

bool SmallCandle(const MqlRates &bar, double atr, string &detail)
  {
   double body = MathAbs(bar.close - bar.open);
   double span = bar.high - bar.low;
   if(span<=0.0 || atr<=0.0)
     {
      detail = "flat candle";
      return false;
     }
   double br = body/span;
   double ar = span/atr;
   detail = StringFormat("body %.2f  range %.2f x ATR", br, ar);
   if(ar < InpNoiseReject)
      return false;
   double maxRange = InpRangeAtr;
   if(br <= InpBodyMax * 0.6)
      maxRange = InpWideSmall;
   return (br<=InpBodyMax && ar<=maxRange);
  }

void ScoreSide(const string side,
               const ScanResult &scan,
               bool uptrend, bool downtrend,
               bool flowBuy, bool flowSell,
               bool chop, bool small, bool brkBuy, bool brkSell,
               SideResult &out)
  {
   out.side = side;
   out.score = 0;
   out.reasons = "";
   out.required = RequiredScore(side, scan.bias);
   bool alignedTrend = (side=="BUY" && uptrend) || (side=="SELL" && downtrend);
   bool alignedFlow  = (side=="BUY" && flowBuy) || (side=="SELL" && flowSell);
   bool broke        = (side=="BUY" && brkBuy) || (side=="SELL" && brkSell);
   bool hard = false;

   if(alignedTrend) out.score++;
   else { out.reasons += "counter-trend; "; hard=true; }

   if(scan.adx >= InpADXMin) out.score++;
   else if(InpUseChopFilter && chop && scan.adx < InpWeakADXLevel)
     { out.reasons += "chop+weak ADX; "; hard=true; }

   if(alignedFlow) out.score++;
   else if(InpRequireM1Flow)
     { out.reasons += "flow against; "; hard=true; }

   if(small) out.score++;
   else { out.reasons += "not small candle; "; hard=true; }

   if(broke) out.score++;
   else out.reasons += "no breakout; ";

   bool rsiOk = (side=="BUY" && scan.rsi<=62.0) || (side=="SELL" && scan.rsi>=38.0);
   if(rsiOk) out.score++;
   else out.reasons += "RSI stretched; ";

   if(!InpUseFlowScore) out.required = 1;

   if(hard || out.score < out.required)
      out.verdict = V_MALI;
   else if(out.score == out.required)
      out.verdict = V_WEAK;
   else
      out.verdict = V_OK;

   if(scan.bias=="WORST")
     {
      out.reasons += "worst hour; ";
      if(out.verdict==V_OK) out.verdict = V_WEAK;
     }
  }

bool RunScan(ScanResult &r)
  {
   MqlRates m5[];
   ArraySetAsSeries(m5, true);
   if(CopyRates(_Symbol, PERIOD_M5, 0, 80, m5) < 60)
     {
      r.overall = V_WAIT;
      r.summary = "WAIT — need M5 history";
      r.preferred = "";
      return false;
     }

   r.hour = TimeHour(m5[1].time);
   r.bias = HourBias(r.hour);

   if(!Copy1(g_m5_fast, 0, 1, r.ema_fast)) return false;
   if(!Copy1(g_m5_slow, 0, 1, r.ema_slow)) return false;
   if(!Copy1(g_m5_adx,  0, 1, r.adx))      return false;
   if(!Copy1(g_m5_rsi,  0, 1, r.rsi))      return false;
   if(!Copy1(g_m5_atr,  0, 1, r.atr))      return false;

   double m1f=0, m1s=0;
   if(!Copy1(g_m1_fast, 0, 1, m1f)) return false;
   if(!Copy1(g_m1_slow, 0, 1, m1s)) return false;

   bool uptrend   = r.ema_fast > r.ema_slow;
   bool downtrend = r.ema_fast < r.ema_slow;
   bool flowBuy   = m1f > m1s;
   bool flowSell  = m1f < m1s;
   double gapPct  = MathAbs(r.ema_fast - r.ema_slow) / m5[1].close * 100.0;
   bool chop      = gapPct < InpChopGapPct;

   string smallDetail;
   bool small = SmallCandle(m5[2], r.atr, smallDetail);
   double buf = InpBreakoutAtr * r.atr;
   bool brkBuy  = small && m5[1].close > m5[2].high + buf;
   bool brkSell = small && m5[1].close < m5[2].low  - buf;

   ScoreSide("BUY",  r, uptrend, downtrend, flowBuy, flowSell, chop, small, brkBuy, brkSell, r.buy);
   ScoreSide("SELL", r, uptrend, downtrend, flowBuy, flowSell, chop, small, brkBuy, brkSell, r.sell);

   SideResult best = r.sell;
   if(r.buy.verdict < r.sell.verdict)
      best = r.buy;
   else if(r.buy.verdict==r.sell.verdict && r.buy.score > r.sell.score)
      best = r.buy;

   r.preferred = "";
   if(best.verdict==V_OK || best.verdict==V_WEAK)
     {
      r.overall = best.verdict;
      r.preferred = best.side;
      r.summary = StringFormat("%s — %s  score %d/%d",
                               VerdictName(best.verdict), best.side, best.score, best.required);
     }
   else
     {
      r.overall = V_MALI;
      r.summary = StringFormat("MALI — huwag i-%s (%s)", best.side, best.reasons);
     }
   return true;
  }

void DelPanel()
  {
   int total = ObjectsTotal(0, 0, -1);
   for(int i=total-1; i>=0; i--)
     {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, g_pfx)==0)
         ObjectDelete(0, name);
     }
  }

void Label(const string id, int y, const string text, color clr, int size=10, bool bold=false)
  {
   string name = g_pfx + id;
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, InpPanelX);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, size);
   ObjectSetString(0, name, OBJPROP_FONT, bold ? "Consolas Bold" : "Consolas");
   ObjectSetString(0, name, OBJPROP_TEXT, text);
  }

void DrawPanel(const ScanResult &r)
  {
   if(!InpShowPanel)
      return;
   int y = InpPanelY;
   color head = VerdictColor(r.overall);
   Label("h1", y, "JM GOLD ANALYZER  " + InpMasterBuildTag, clrWhite, 11, true); y+=18;
   Label("h2", y, StringFormat("%s  M5   lots %.2f   %s",
         _Symbol, InpLots, EnumToString(InpTradeMode)), clrSilver, 9); y+=16;
   Label("v",  y, "VERDICT  " + VerdictName(r.overall) + "   " + r.summary, head, 11, true); y+=20;
   Label("hr", y, StringFormat("Hour %02d:00  bias %s", r.hour, r.bias),
         r.bias=="WORST" ? clrTomato : clrGainsboro, 9); y+=16;
   Label("tr", y, StringFormat("M5 EMA %s / %s   ADX %.1f   RSI %.1f",
         DoubleToString(r.ema_fast, 2), DoubleToString(r.ema_slow, 2), r.adx, r.rsi),
         clrGainsboro, 9); y+=18;
   color bc = VerdictColor(r.buy.verdict);
   color sc = VerdictColor(r.sell.verdict);
   Label("b",  y, StringFormat("BUY   %s   score %d/%d   %s",
         VerdictName(r.buy.verdict), r.buy.score, r.buy.required, r.buy.reasons), bc, 10); y+=16;
   Label("s",  y, StringFormat("SELL  %s   score %d/%d   %s",
         VerdictName(r.sell.verdict), r.sell.score, r.sell.required, r.sell.reasons), sc, 10); y+=18;
   Label("a",  y, "Last: " + g_last_action, clrSilver, 9);
   ChartRedraw();
  }

bool HasOurPosition()
  {
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket==0) continue;
      if(PositionGetString(POSITION_SYMBOL)==_Symbol &&
         PositionGetInteger(POSITION_MAGIC)==InpMagic)
         return true;
     }
   return false;
  }

void MaybeTrade(const ScanResult &r, datetime bar_time)
  {
   if(InpTradeMode==MODE_ANALYZER_ONLY)
     {
      g_last_action = "analyzer only — no order";
      return;
     }
   if(HasOurPosition())
     {
      g_last_action = "flat wait — position open";
      return;
     }
   if(r.preferred=="")
     {
      g_last_action = "SKIP MALI — " + r.summary;
      Print("JM Analyzer SKIP: ", r.summary);
      return;
     }
   int v = (r.preferred=="BUY") ? r.buy.verdict : r.sell.verdict;
   if(v==V_MALI || v==V_WAIT)
     {
      g_last_action = "SKIP MALI " + r.preferred;
      return;
     }
   if(InpTradeMode==MODE_OK_ONLY && v!=V_OK)
     {
      g_last_action = "SKIP WEAK (OK-only mode) " + r.preferred;
      return;
     }
   if(r.preferred=="BUY" && !InpAllowBuy)
     {
      g_last_action = "BUY blocked by InpAllowBuy=false";
      return;
     }
   if(r.preferred=="SELL" && !InpAllowSell)
     {
      g_last_action = "SELL blocked by InpAllowSell=false";
      return;
     }

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double sl, tp;
   ENUM_ORDER_TYPE type;
   if(r.preferred=="BUY")
     {
      type = ORDER_TYPE_BUY;
      sl = ask - InpSLPrice;
      tp = ask + InpTPPrice;
     }
   else
     {
      type = ORDER_TYPE_SELL;
      sl = bid + InpSLPrice;
      tp = bid - InpTPPrice;
     }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   string cmt = StringFormat("%s %s sc%d/%d", VerdictName(v), r.preferred,
                             (r.preferred=="BUY"?r.buy.score:r.sell.score),
                             (r.preferred=="BUY"?r.buy.required:r.sell.required));
   bool ok;
   if(type==ORDER_TYPE_BUY)
      ok = trade.Buy(InpLots, _Symbol, ask, sl, tp, cmt);
   else
      ok = trade.Sell(InpLots, _Symbol, bid, sl, tp, cmt);

   if(ok)
     {
      g_last_action = StringFormat("ENTER %s @ %s  %s", r.preferred,
                                   DoubleToString(type==ORDER_TYPE_BUY?ask:bid, _Digits), cmt);
      Print("JM Analyzer ENTER ", g_last_action);
     }
   else
     {
      g_last_action = "ORDER FAIL " + IntegerToString(trade.ResultRetcode()) + " " + trade.ResultRetcodeDescription();
      Print("JM Analyzer ", g_last_action);
     }
  }

int OnInit()
  {
   if(InpSymbol!="" && _Symbol!=InpSymbol)
      Print("JM Analyzer: attached to ", _Symbol, " (input symbol ", InpSymbol, ")");

   g_m5_fast = iMA(_Symbol, PERIOD_M5, InpM5FastEMA, 0, MODE_EMA, PRICE_CLOSE);
   g_m5_slow = iMA(_Symbol, PERIOD_M5, InpM5SlowEMA, 0, MODE_EMA, PRICE_CLOSE);
   g_m5_adx  = iADX(_Symbol, PERIOD_M5, InpM5ADXPeriod);
   g_m5_rsi  = iRSI(_Symbol, PERIOD_M5, InpM1RSIPeriod, PRICE_CLOSE);
   g_m5_atr  = iATR(_Symbol, PERIOD_M5, InpM1ATRPeriod);
   g_m1_fast = iMA(_Symbol, PERIOD_M1, InpM1FastEMA, 0, MODE_EMA, PRICE_CLOSE);
   g_m1_slow = iMA(_Symbol, PERIOD_M1, InpM1SlowEMA, 0, MODE_EMA, PRICE_CLOSE);

   if(g_m5_fast==INVALID_HANDLE || g_m5_slow==INVALID_HANDLE || g_m5_adx==INVALID_HANDLE ||
      g_m5_rsi==INVALID_HANDLE || g_m5_atr==INVALID_HANDLE ||
      g_m1_fast==INVALID_HANDLE || g_m1_slow==INVALID_HANDLE)
     {
      Print("JM Analyzer: indicator handle failed");
      return INIT_FAILED;
     }

   trade.SetExpertMagicNumber(InpMagic);
   ChartSetInteger(0, CHART_SHOW_GRID, false);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   DelPanel();
   IndicatorRelease(g_m5_fast);
   IndicatorRelease(g_m5_slow);
   IndicatorRelease(g_m5_adx);
   IndicatorRelease(g_m5_rsi);
   IndicatorRelease(g_m5_atr);
   IndicatorRelease(g_m1_fast);
   IndicatorRelease(g_m1_slow);
  }

void OnTick()
  {
   ScanResult r;
   ZeroMemory(r);
   r.buy.verdict = V_WAIT;
   r.sell.verdict = V_WAIT;
   r.overall = V_WAIT;
   r.summary = "scanning…";
   if(!RunScan(r))
     {
      r.overall = V_WAIT;
      if(r.summary=="")
         r.summary = "WAIT — indicators";
     }

   datetime bar = iTime(_Symbol, PERIOD_M5, 1);
   if(bar!=g_last_bar && r.overall!=V_WAIT)
     {
      g_last_bar = bar;
      MaybeTrade(r, bar);
     }
   DrawPanel(r);
  }
