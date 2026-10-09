#property strict
#property version "1.30"
#property description "JM MTF Volume Profile Scalper - H1 M15 M1 + chart VP/OB"

#include <Trade/Trade.mqh>
CTrade trade;

// ================= SETTINGS =================
input group "General"
input double Lots = 0.01;
input bool EnableAutoTrading = false;
input ulong MagicNumber = 20261010;
input int MaxSpreadPoints = 350;
input int SlippagePoints = 30;

input group "H1 Trend"
input int FastEMA = 50;
input int SlowEMA = 200;

input group "M15 Volume Profile"
input int ProfileBars = 96;
input int ProfileBins = 40;
input double ZoneWidthATR = 0.35;
input int ATRPeriod = 14;

input group "M15 Small Candle"
input double MaxBodyRatio = 0.30;
input double MinWickBodyRatio = 1.5;
input int ConfirmationMinutes = 15;

input group "M1 Confirmation"
input int StructureLookback = 5;
input double MinConfirmBodyRatio = 0.50;

input group "Risk Management"
input double RiskReward = 2.0;
input int SLBufferPoints = 100;
input int MinSLPoints = 100;
input int MaxSLPoints = 5000;

input group "Chart display (like JM MTF diagram)"
input bool ShowVolumeHistogram = true;
input bool ShowOrderBlocks = true;
input bool ShowH1SupplyDemand = true;
input int HistogramMaxMinutes = 480;
input int H1SwingLookback = 48;
input int OrderBlockLookback = 24;

// ================= GLOBALS =================
int fastHandle, slowHandle, atrHandle;
datetime lastM1Bar = 0;
datetime lastSignalTime = 0;
datetime lastTradedSignal = 0;

double poc = 0;
double zoneLow = 0;
double zoneHigh = 0;
double signalHigh = 0;
double signalLow = 0;

int signalDirection = 0;

double g_profileLow = 0;
double g_profileHigh = 0;
double g_profileStep = 0;
double g_profileVolumes[];

// ================= UTILITIES =================
void DeleteObjectsWithPrefix(string prefix)
{
   int total = ObjectsTotal(0, 0, -1);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, prefix) == 0)
         ObjectDelete(0, name);
   }
}

void DrawLabel(string name, datetime t, double price, string text, color clr)
{
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_TEXT, 0, t, price);

   ObjectMove(0, name, 0, t, price);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
   ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT);
}

void DrawZoneRect(string name, datetime t1, datetime t2,
                  double hi, double lo, color clr, string label)
{
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, hi, t2, lo);

   ObjectMove(0, name, 0, t1, hi);
   ObjectMove(0, name, 1, t2, lo);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);

   DrawLabel(name + "_LBL", t2, (hi + lo) / 2.0, label, clr);
}

double NormalizePrice(double price)
{
   return NormalizeDouble(price, _Digits);
}

bool IsNewBar(ENUM_TIMEFRAMES tf, datetime &last)
{
   datetime t = iTime(_Symbol, tf, 0);
   if(t <= 0 || t == last)
      return false;

   last = t;
   return true;
}

double GetATR()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);

   if(CopyBuffer(atrHandle, 0, 1, 1, buffer) != 1)
      return 0;

   return buffer[0];
}

int GetTrend()
{
   double fast[], slow[];
   ArraySetAsSeries(fast, true);
   ArraySetAsSeries(slow, true);

   if(CopyBuffer(fastHandle, 0, 1, 1, fast) != 1)
      return 0;

   if(CopyBuffer(slowHandle, 0, 1, 1, slow) != 1)
      return 0;

   double close = iClose(_Symbol, PERIOD_H1, 1);

   if(close > fast[0] && fast[0] > slow[0])
      return 1;

   if(close < fast[0] && fast[0] < slow[0])
      return -1;

   return 0;
}

// ================= VOLUME PROFILE =================
// Approximation using M15 tick volume.
// Volume is distributed across each candle's price range.
bool CalculateVolumeProfile()
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);

   int count = CopyRates(
      _Symbol, PERIOD_M15, 1, ProfileBars, rates
   );

   if(count < 20 || ProfileBins < 5)
      return false;

   double lowest = DBL_MAX;
   double highest = -DBL_MAX;

   for(int i = 0; i < count; i++)
   {
      lowest = MathMin(lowest, rates[i].low);
      highest = MathMax(highest, rates[i].high);
   }

   double step = (highest - lowest) / ProfileBins;

   if(step <= 0)
      return false;

   double volumes[];
   ArrayResize(volumes, ProfileBins);
   ArrayInitialize(volumes, 0);

   for(int i = 0; i < count; i++)
   {
      int first = (int)MathFloor(
         (rates[i].low - lowest) / step
      );

      int last = (int)MathFloor(
         (rates[i].high - lowest) / step
      );

      first = MathMax(0, MathMin(ProfileBins-1, first));
      last = MathMax(0, MathMin(ProfileBins-1, last));

      int binsCovered = last - first + 1;
      if(binsCovered <= 0)
         continue;

      double volumePerBin =
         (double)rates[i].tick_volume / binsCovered;

      for(int j = first; j <= last; j++)
         volumes[j] += volumePerBin;
   }

   int maxIndex = 0;

   for(int i = 1; i < ProfileBins; i++)
   {
      if(volumes[i] > volumes[maxIndex])
         maxIndex = i;
   }

   poc = NormalizePrice(
      lowest + (maxIndex + 0.5) * step
   );

   double atr = GetATR();
   if(atr <= 0)
      return false;

   double width = atr * ZoneWidthATR;

   zoneLow = NormalizePrice(poc - width);
   zoneHigh = NormalizePrice(poc + width);

   g_profileLow = lowest;
   g_profileHigh = highest;
   g_profileStep = step;
   ArrayResize(g_profileVolumes, ProfileBins);
   for(int k = 0; k < ProfileBins; k++)
      g_profileVolumes[k] = volumes[k];

   return true;
}

bool IsSwingHigh(ENUM_TIMEFRAMES tf, int shift, int wing)
{
   double h = iHigh(_Symbol, tf, shift);
   for(int j = 1; j <= wing; j++)
   {
      if(iHigh(_Symbol, tf, shift + j) >= h)
         return false;
      if(iHigh(_Symbol, tf, shift - j) <= 0)
         return false;
      if(iHigh(_Symbol, tf, shift - j) >= h)
         return false;
   }
   return true;
}

bool IsSwingLow(ENUM_TIMEFRAMES tf, int shift, int wing)
{
   double lo = iLow(_Symbol, tf, shift);
   for(int j = 1; j <= wing; j++)
   {
      if(iLow(_Symbol, tf, shift + j) <= lo)
         return false;
      if(iLow(_Symbol, tf, shift - j) <= 0)
         return false;
      if(iLow(_Symbol, tf, shift - j) <= lo)
         return false;
   }
   return true;
}

bool FindOrderBlock(ENUM_TIMEFRAMES tf, int bias, int lookback,
                    double &obHigh, double &obLow, datetime &obTime)
{
   MqlRates bars[];
   ArraySetAsSeries(bars, true);
   int n = CopyRates(_Symbol, tf, 1, lookback, bars);
   if(n < 6)
      return false;

   int start = MathMin(n - 2, lookback - 2);
   for(int i = 2; i < start; i++)
   {
      if(bias > 0)
      {
         if(bars[i].close < bars[i].open &&
            bars[i - 1].close > bars[i - 1].open &&
            bars[i - 1].close > bars[i].high)
         {
            obHigh = bars[i].high;
            obLow = bars[i].low;
            obTime = bars[i].time;
            return true;
         }
      }
      else if(bias < 0)
      {
         if(bars[i].close > bars[i].open &&
            bars[i - 1].close < bars[i - 1].open &&
            bars[i - 1].close < bars[i].low)
         {
            obHigh = bars[i].high;
            obLow = bars[i].low;
            obTime = bars[i].time;
            return true;
         }
      }
   }

   // Fallback: last opposite candle (SMC-style)
   for(int i = 1; i < n - 1; i++)
   {
      if(bias > 0 && bars[i].close < bars[i].open)
      {
         obHigh = bars[i].high;
         obLow = bars[i].low;
         obTime = bars[i].time;
         return true;
      }
      if(bias < 0 && bars[i].close > bars[i].open)
      {
         obHigh = bars[i].high;
         obLow = bars[i].low;
         obTime = bars[i].time;
         return true;
      }
   }
   return false;
}

void DrawVolumeHistogram()
{
   if(!ShowVolumeHistogram || ArraySize(g_profileVolumes) < ProfileBins)
      return;

   DeleteObjectsWithPrefix("JM_VP_");

   double maxVol = 0;
   for(int i = 0; i < ProfileBins; i++)
      maxVol = MathMax(maxVol, g_profileVolumes[i]);

   if(maxVol <= 0 || g_profileStep <= 0)
      return;

   datetime tAnchor = iTime(_Symbol, PERIOD_M15, ProfileBars);
   if(tAnchor <= 0)
      tAnchor = iTime(_Symbol, PERIOD_M15, 1);

   int spanSec = HistogramMaxMinutes * 60;

   for(int i = 0; i < ProfileBins; i++)
   {
      double lo = g_profileLow + i * g_profileStep;
      double hi = lo + g_profileStep;
      int widthSec = (int)(spanSec * (g_profileVolumes[i] / maxVol));
      if(widthSec < PeriodSeconds(PERIOD_M15) / 4)
         continue;

      datetime t2 = tAnchor + widthSec;
      string name = "JM_VP_" + IntegerToString(i);

      color barClr = clrDodgerBlue;
      if(MathAbs((lo + hi) / 2.0 - poc) <= g_profileStep * 1.5)
         barClr = clrOrange;
      else if((lo + hi) / 2.0 > poc)
         barClr = clrCornflowerBlue;

      if(ObjectFind(0, name) < 0)
         ObjectCreate(0, name, OBJ_RECTANGLE, 0, tAnchor, hi, t2, lo);

      ObjectMove(0, name, 0, tAnchor, hi);
      ObjectMove(0, name, 1, t2, lo);
      ObjectSetInteger(0, name, OBJPROP_COLOR, barClr);
      ObjectSetInteger(0, name, OBJPROP_FILL, true);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   }
}

void DrawH1SupplyDemand(int trend)
{
   if(!ShowH1SupplyDemand || trend == 0)
      return;

   DeleteObjectsWithPrefix("JM_H1Z_");

   double atr = GetATR();
   if(atr <= 0)
      atr = _Point * 100;

   datetime t1 = iTime(_Symbol, PERIOD_H1, H1SwingLookback);
   datetime t2 = TimeCurrent() + PeriodSeconds(PERIOD_H1) * 6;

   for(int i = 2; i < H1SwingLookback - 2; i++)
   {
      if(trend < 0 && IsSwingHigh(PERIOD_H1, i, 2))
      {
         double sh = iHigh(_Symbol, PERIOD_H1, i);
         double zHi = sh + atr * 0.08;
         double zLo = sh - atr * 0.22;
         DrawZoneRect("JM_H1Z_SUPPLY", t1, t2, zHi, zLo,
                      clrMediumPurple, "H1 SUPPLY ZONE");
         {
            double slow[];
            ArraySetAsSeries(slow, true);
            if(CopyBuffer(slowHandle, 0, 1, 1, slow) == 1)
               DrawLine("JM_H1_EMA200", slow[0], clrWhite, STYLE_DOT);
         }
         return;
      }
      if(trend > 0 && IsSwingLow(PERIOD_H1, i, 2))
      {
         double sl = iLow(_Symbol, PERIOD_H1, i);
         double zLo = sl - atr * 0.08;
         double zHi = sl + atr * 0.22;
         DrawZoneRect("JM_H1Z_DEMAND", t1, t2, zHi, zLo,
                      clrSeaGreen, "H1 DEMAND ZONE");
         return;
      }
   }
}

void DrawOrderBlocks(int trend)
{
   if(!ShowOrderBlocks || trend == 0)
      return;

   DeleteObjectsWithPrefix("JM_OB_");

   datetime tEnd = TimeCurrent() + PeriodSeconds(PERIOD_M15) * 8;
   double obH = 0, obL = 0;
   datetime obT = 0;

   if(FindOrderBlock(PERIOD_M15, trend, OrderBlockLookback, obH, obL, obT))
   {
      DrawZoneRect("JM_OB_M15", obT, tEnd, obH, obL,
                   trend < 0 ? clrIndianRed : clrMediumSeaGreen,
                   trend < 0 ? "M15 SELL OB" : "M15 BUY OB");
   }

   if(FindOrderBlock(PERIOD_H1, trend, MathMax(12, OrderBlockLookback / 2),
                      obH, obL, obT))
   {
      DrawZoneRect("JM_OB_H1", obT, tEnd, obH, obL,
                   trend < 0 ? clrFireBrick : clrDarkGreen,
                   trend < 0 ? "H1 SELL OB" : "H1 BUY OB");
   }
}

void DrawChartVisuals(int trend)
{
   DrawVolumeHistogram();
   DrawH1SupplyDemand(trend);
   DrawOrderBlocks(trend);
}

// ================= CHART DRAWING =================
void DrawLine(string name, double price, color clr,
              ENUM_LINE_STYLE style = STYLE_SOLID)
{
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);

   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
}

void DrawZone()
{
   datetime start = iTime(
      _Symbol, PERIOD_M15, ProfileBars
   );

   datetime finish = TimeCurrent() + 86400;

   string name = "JM_VOLUME_ZONE";

   if(ObjectFind(0, name) < 0)
      ObjectCreate(
         0, name, OBJ_RECTANGLE, 0,
         start, zoneHigh, finish, zoneLow
      );

   ObjectMove(0, name, 0, start, zoneHigh);
   ObjectMove(0, name, 1, finish, zoneLow);

   ObjectSetInteger(0, name, OBJPROP_COLOR, clrMediumPurple);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);

   DrawLine("JM_POC", poc, clrOrange, STYLE_DASH);
   DrawLabel("JM_POC_LBL", finish, poc, "POC / M15 SUPPLY ZONE", clrOrange);
}

void DrawArrow(string name, datetime time,
               double price, bool buy)
{
   if(ObjectFind(0, name) >= 0)
      return;

   ObjectCreate(0, name, OBJ_ARROW, 0, time, price);

   ObjectSetInteger(
      0, name, OBJPROP_ARROWCODE, buy ? 233 : 234
   );

   ObjectSetInteger(
      0, name, OBJPROP_COLOR,
      buy ? clrLime : clrRed
   );

   ObjectSetInteger(0, name, OBJPROP_WIDTH, 3);
}

// ================= M15 SIGNAL =================
void DetectM15Signal()
{
   signalDirection = 0;

   int trend = GetTrend();
   if(trend == 0)
      return;

   MqlRates candle[];
   ArraySetAsSeries(candle, true);

   if(CopyRates(_Symbol, PERIOD_M15, 1, 1, candle) != 1)
      return;

   double range = candle[0].high - candle[0].low;
   if(range <= 0)
      return;

   double body = MathAbs(
      candle[0].close - candle[0].open
   );

   double upperWick =
      candle[0].high -
      MathMax(candle[0].open, candle[0].close);

   double lowerWick =
      MathMin(candle[0].open, candle[0].close) -
      candle[0].low;

   bool smallCandle = body / range <= MaxBodyRatio;

   if(!smallCandle)
      return;

   bool touchesZone =
      candle[0].high >= zoneLow &&
      candle[0].low <= zoneHigh;

   if(!touchesZone)
      return;

   double minWick = MathMax(body, _Point);

   bool bullishRejection =
      lowerWick >= minWick * MinWickBodyRatio &&
      candle[0].close >= zoneLow;

   bool bearishRejection =
      upperWick >= minWick * MinWickBodyRatio &&
      candle[0].close <= zoneHigh;

   if(trend == 1 && bullishRejection)
      signalDirection = 1;

   if(trend == -1 && bearishRejection)
      signalDirection = -1;

   if(signalDirection == 0)
      return;

   signalHigh = candle[0].high;
   signalLow = candle[0].low;
   lastSignalTime = candle[0].time + 900;

   DrawArrow(
      "JM_M15_SIGNAL_" + IntegerToString(
         (long)candle[0].time
      ),
      candle[0].time,
      signalDirection == 1 ? signalLow : signalHigh,
      signalDirection == 1
   );
}

// ================= M1 CONFIRMATION =================
bool ConfirmM1()
{
   if(signalDirection == 0)
      return false;

   if(TimeCurrent() - lastSignalTime >
      ConfirmationMinutes * 60)
   {
      signalDirection = 0;
      return false;
   }

   if(TimeCurrent() < lastSignalTime)
      return false;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);

   int needed = StructureLookback + 2;

   if(CopyRates(
      _Symbol, PERIOD_M1, 1, needed, rates
   ) < needed)
      return false;

   double range = rates[0].high - rates[0].low;

   if(range <= 0)
      return false;

   double body = MathAbs(
      rates[0].close - rates[0].open
   );

   if(body / range < MinConfirmBodyRatio)
      return false;

   double structureHigh = -DBL_MAX;
   double structureLow = DBL_MAX;

   for(int i = 1; i <= StructureLookback; i++)
   {
      structureHigh = MathMax(
         structureHigh, rates[i].high
      );

      structureLow = MathMin(
         structureLow, rates[i].low
      );
   }

   if(signalDirection == 1)
   {
      return (
         rates[0].close > rates[0].open &&
         rates[0].close > structureHigh &&
         rates[0].close > signalHigh
      );
   }

   return (
      rates[0].close < rates[0].open &&
      rates[0].close < structureLow &&
      rates[0].close < signalLow
   );
}

// ================= POSITION CHECK =================
bool HasOpenPosition()
{
   for(int i = PositionsTotal()-1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);

      if(ticket == 0)
         continue;

      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC)
         == MagicNumber)
         return true;
   }

   return false;
}

// ================= EXECUTE TRADE =================
void ExecuteTrade()
{
   if(lastTradedSignal == lastSignalTime)
      return;

   if(HasOpenPosition())
      return;

   MqlTick tick;

   if(!SymbolInfoTick(_Symbol, tick))
      return;

   double spread = (tick.ask - tick.bid) / _Point;

   if(spread > MaxSpreadPoints)
      return;

   bool buy = signalDirection == 1;

   double entry = buy ? tick.ask : tick.bid;

   double sl = buy ?
      signalLow - SLBufferPoints * _Point :
      signalHigh + SLBufferPoints * _Point;

   sl = NormalizePrice(sl);

   double distance = MathAbs(entry - sl);
   double distancePoints = distance / _Point;

   if(buy && sl >= entry)
      return;

   if(!buy && sl <= entry)
      return;

   if(distancePoints < MinSLPoints ||
      distancePoints > MaxSLPoints)
      return;

   long stopsLevel = SymbolInfoInteger(
      _Symbol, SYMBOL_TRADE_STOPS_LEVEL
   );

   if(distancePoints <= stopsLevel)
      return;

   double tp = buy ?
      entry + distance * RiskReward :
      entry - distance * RiskReward;

   tp = NormalizePrice(tp);

   string prefix =
      "JM_TRADE_" + IntegerToString(
         (long)lastSignalTime
      );

   DrawLine(prefix + "_ENTRY", entry, clrDodgerBlue);
   DrawLine(prefix + "_SL", sl, clrRed);
   DrawLine(prefix + "_TP", tp, clrLime);

   DrawArrow(
      prefix + "_ARROW",
      TimeCurrent(), entry, buy
   );

   if(!EnableAutoTrading)
   {
      Print(
         "JM SIGNAL ONLY: ",
         buy ? "BUY" : "SELL",
         " Entry=", entry,
         " SL=", sl,
         " TP=", tp
      );

      lastTradedSignal = lastSignalTime;
      signalDirection = 0;
      return;
   }

   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ||
      !MQLInfoInteger(MQL_TRADE_ALLOWED))
      return;

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(SlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   bool sent = false;

   if(buy)
      sent = trade.Buy(
         Lots, _Symbol, 0, sl, tp, "JM MTF BUY"
      );
   else
      sent = trade.Sell(
         Lots, _Symbol, 0, sl, tp, "JM MTF SELL"
      );

   uint result = trade.ResultRetcode();

   if(sent &&
      (result == TRADE_RETCODE_DONE ||
       result == TRADE_RETCODE_DONE_PARTIAL))
   {
      lastTradedSignal = lastSignalTime;
      signalDirection = 0;

      Print("JM MTF trade executed: ", result);
   }
   else
   {
      Print(
         "Order failed: ",
         result, " ",
         trade.ResultRetcodeDescription()
      );
   }
}

// ================= INITIALIZATION =================
int OnInit()
{
   if(ProfileBars < 20 || ProfileBins < 5 ||
      StructureLookback < 2 ||
      FastEMA <= 0 || SlowEMA <= FastEMA ||
      ATRPeriod <= 0 || Lots <= 0 ||
      RiskReward <= 0)
   {
      Print("Invalid EA input settings");
      return INIT_PARAMETERS_INCORRECT;
   }

   fastHandle = iMA(
      _Symbol, PERIOD_H1, FastEMA, 0,
      MODE_EMA, PRICE_CLOSE
   );

   slowHandle = iMA(
      _Symbol, PERIOD_H1, SlowEMA, 0,
      MODE_EMA, PRICE_CLOSE
   );

   atrHandle = iATR(
      _Symbol, PERIOD_M15, ATRPeriod
   );

   if(fastHandle == INVALID_HANDLE ||
      slowHandle == INVALID_HANDLE ||
      atrHandle == INVALID_HANDLE)
   {
      Print("Indicator initialization failed");
      return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(SlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   lastM1Bar = iTime(_Symbol, PERIOD_M1, 0);

   Print("JM MTF Volume Profile Scalper v1.30 loaded (VP histogram + OB zones)");

   return INIT_SUCCEEDED;
}

// ================= MAIN LOOP =================
void OnTick()
{
   if(!IsNewBar(PERIOD_M1, lastM1Bar))
      return;

   if(CalculateVolumeProfile())
   {
      int trend = GetTrend();
      DrawZone();
      DrawChartVisuals(trend);

      // Detect the latest closed M15 signal
      // only after its close.
      datetime closedM15 =
         iTime(_Symbol, PERIOD_M15, 1);

      datetime signalClosedAt = closedM15 + 900;

      if(signalClosedAt > lastSignalTime &&
         TimeCurrent() >= signalClosedAt)
      {
         DetectM15Signal();
      }
   }

   if(signalDirection == 0)
      return;

   if(ConfirmM1())
      ExecuteTrade();
}

// ================= CLEANUP =================
void OnDeinit(const int reason)
{
   if(fastHandle != INVALID_HANDLE)
      IndicatorRelease(fastHandle);

   if(slowHandle != INVALID_HANDLE)
      IndicatorRelease(slowHandle);

   if(atrHandle != INVALID_HANDLE)
      IndicatorRelease(atrHandle);

   DeleteObjectsWithPrefix("JM_VP_");
   DeleteObjectsWithPrefix("JM_OB_");
   DeleteObjectsWithPrefix("JM_H1Z_");
   ObjectDelete(0, "JM_VOLUME_ZONE");
   ObjectDelete(0, "JM_POC");
   ObjectDelete(0, "JM_POC_LBL");

   Print("JM MTF Volume Profile Scalper stopped");
}
