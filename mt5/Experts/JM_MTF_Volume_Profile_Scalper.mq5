#property strict
#property version "1.20"
#property description "JM MTF Volume Profile Scalper - H1 M15 M1"

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

// ================= UTILITIES =================
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

   return true;
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

   Print("JM MTF Volume Profile Scalper v1.20 loaded");

   return INIT_SUCCEEDED;
}

// ================= MAIN LOOP =================
void OnTick()
{
   if(!IsNewBar(PERIOD_M1, lastM1Bar))
      return;

   if(CalculateVolumeProfile())
   {
      DrawZone();

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

   Print("JM MTF Volume Profile Scalper stopped");
}
