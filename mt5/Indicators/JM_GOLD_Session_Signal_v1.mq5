//+------------------------------------------------------------------+
//| JM_GOLD_Session_Signal_v1.mq5                                    |
//| Visual GOLD# validator: PH sessions + V6.77 scalper dots         |
//| NO ORDERS. CSV reason log for later EA conversion.               |
//+------------------------------------------------------------------+
#property copyright "JM Tech Solution"
#property version   "1.31"
#property description "V6.77 scalper dots on TOP of signal candles. Lime BUY / red SELL. No auto trade."
#property indicator_chart_window
#property indicator_buffers 4
#property indicator_plots   4

#property indicator_label1  "BUY"
#property indicator_type1   DRAW_ARROW
#property indicator_color1  clrLime
#property indicator_width1  3

#property indicator_label2  "SELL"
#property indicator_type2   DRAW_ARROW
#property indicator_color2  clrRed
#property indicator_width2  3

#property indicator_label3  "BIAS"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrGold
#property indicator_style3  STYLE_SOLID
#property indicator_width3  2

#property indicator_label4  "FAST"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrAqua
#property indicator_style4  STYLE_SOLID
#property indicator_width4  1

#define PREFIX "JMSS_"
#define CSV_NAME "JM_GOLD_Session_Signal_v1.csv"
#define DOT_CODE 159

input group "=== PH sessions (UTC+8) ==="
input int    InpPhUtcOffset         = 8;
input int    InpDaysBack            = 7;
input bool   InpDrawDaily           = true;
input bool   InpDrawSessions        = true;
input bool   InpDrawOpenLines       = true;
input bool   InpDrawPhHours         = true;
input bool   InpDrawHourLines       = false;
input int    InpHourFontSize        = 8;
input double InpHourLabelPadUsd     = 1.50;
input int    InpAsiaStart           = 8;
input int    InpAsiaEnd             = 16;
input int    InpLondonStart         = 15;
input int    InpLondonEnd           = 0;
input int    InpNyStart             = 20;
input int    InpNyEnd               = 5;
input int    InpOverlapStart        = 20;
input int    InpOverlapEnd          = 0;
input color  InpClrDaily            = C'55,55,70';
input color  InpClrAsia             = C'210,160,50';
input color  InpClrLondon           = C'50,110,210';
input color  InpClrNy               = C'30,150,80';
input color  InpClrOverlap          = C'170,70,190';
input int    InpZoneAlpha           = 28;

input group "=== V6.77 scalper (M5 bias + M1 small/break) ==="
input int    InpM5FastEMA           = 20;
input int    InpM5SlowEMA           = 50;
input int    InpM5ADXPeriod         = 14;
input double InpMinADX              = 16.0;
input bool   InpBlockMidADX         = true;
input double InpBlockADXFrom        = 25.0;
input double InpBlockADXTo          = 35.0;
input bool   InpBlockBuyWeakEmaGap  = true;
input double InpBuyWeakGapATR       = 0.25;
input int    InpM1FastEMA           = 9;
input int    InpM1SlowEMA           = 21;
input int    InpM1RSIPeriod         = 14;
input int    InpM1ATRPeriod         = 14;
input double InpSmallBodyRatioMax   = 0.45;
input double InpBreakBufferATR      = 0.05;
input bool   InpRequireM1Flow       = true;
input bool   InpUseChopFilter       = true;
input double InpMinM5GapATR         = 0.06;
input double InpWeakADXLevel        = 20.0;
input double InpMinSmallRangeATR    = 0.15;
input double InpMaxSmallRangeATR    = 0.80;
input bool   InpUseFlowScore        = true;
input int    InpMinFlowScore        = 3;
input double InpBuyRSIMin           = 46.0;
input double InpBuyRSIMax           = 68.0;
input double InpSellRSIMin          = 32.0;
input double InpSellRSIMax          = 54.0;
input bool   InpUseV640ProfitHourRouter = true;
input bool   InpBest4HoursOnly      = false;
input bool   InpV641BlockSellADX20To25 = true;
input double InpV641SellADXBlockFrom   = 20.0;
input double InpV641SellADXBlockTo     = 25.0;
input bool   InpV642BlockBuyGap050To100 = true;
input double InpV642BuyGapBlockFrom     = 0.50;
input double InpV642BuyGapBlockTo       = 1.00;
input bool   InpV643BlockSellGap075To100 = true;
input double InpV643SellGapBlockFrom     = 0.75;
input double InpV643SellGapBlockTo       = 1.00;
input double InpArrowOffsetUsd      = 2.50;   // pad above the wick
input int    InpMinBarsBetween      = 1;
input int    InpMaxLabels           = 25;
input bool   InpShowHourBlockedSetups = true; // yellow/orange dot if strategy OK but V640 hour OFF

input group "=== HTF mix (H1+M30 required, H4 display) ==="
input int    InpH4Fast              = 20;
input int    InpH4Slow              = 50;
input int    InpH1Fast              = 20;
input int    InpH1Slow              = 50;
input int    InpM30Fast             = 20;
input int    InpM30Slow             = 50;
input bool   InpRequireH1           = true;
input bool   InpRequireM30          = true;
input bool   InpRequireH4           = false;

input group "=== Display / log ==="
input bool   InpShowPanel           = true;
input bool   InpShowSignalCards     = false;
input bool   InpLogCsv              = true;
input bool   InpDrawH4Sr            = true;
input bool   InpShowBiasLine        = true;
input bool   InpShowFastEma         = true;

double BufBuy[];
double BufSell[];
double BufBias[];
double BufFast[];
int hM5Fast=INVALID_HANDLE,hM5Slow=INVALID_HANDLE,hM5ADX=INVALID_HANDLE,hM5ATR=INVALID_HANDLE;
int hM1Fast=INVALID_HANDLE,hM1Slow=INVALID_HANDLE,hM1RSI=INVALID_HANDLE,hM1ATR=INVALID_HANDLE;
int hH1F=INVALID_HANDLE,hH1S=INVALID_HANDLE;
int hH4F=INVALID_HANDLE,hH4S=INVALID_HANDLE;
int hM30F=INVALID_HANDLE,hM30S=INVALID_HANDLE;
int g_lastPhYmd=-1;
int g_lastPhHour=-1;
int g_gmtOff=0;
string g_lastReason="";
string g_lastSide="";
string g_lastClock="";
int    g_signalCount=0;
int    g_waitCount=0;
int    g_m1Bars=0;

int BrokerGmtOff() { return (int)(TimeCurrent()-TimeGMT()); }
datetime BrokerToPh(const datetime br) { return br - g_gmtOff + InpPhUtcOffset*3600; }
datetime PhToBroker(const datetime ph) { return ph - InpPhUtcOffset*3600 + g_gmtOff; }

bool InHourRange(const int hour,const int start,const int end)
{
   int h=((hour%24)+24)%24;
   int s=((start%24)+24)%24;
   int e=((end%24)+24)%24;
   if(s==e) return true;
   if(s<e) return (h>=s && h<e);
   return (h>=s || h<e);
}

string SessionName(const int hour)
{
   if(InHourRange(hour,InpOverlapStart,InpOverlapEnd)) return "LONDON-NY OVERLAP";
   if(InHourRange(hour,InpNyStart,InpNyEnd))           return "NEW YORK";
   if(InHourRange(hour,InpLondonStart,InpLondonEnd))   return "LONDON";
   if(InHourRange(hour,InpAsiaStart,InpAsiaEnd))       return "ASIAN/TOKYO";
   return "OFF-HOURS";
}

string FormatPhClock(const datetime ph)
{
   MqlDateTime t; TimeToStruct(ph,t);
   int h12=t.hour%12; if(h12==0) h12=12;
   return StringFormat("%d:%02d %s",h12,t.min,(t.hour>=12?"PM":"AM"));
}

string FormatPhHour(const int hour)
{
   int h=((hour%24)+24)%24;
   int h12=h%12; if(h12==0) h12=12;
   return StringFormat("%d%s",h12,(h>=12?"PM":"AM"));
}

color SessionColor(const int hour)
{
   if(InHourRange(hour,InpOverlapStart,InpOverlapEnd)) return InpClrOverlap;
   if(InHourRange(hour,InpNyStart,InpNyEnd))           return InpClrNy;
   if(InHourRange(hour,InpLondonStart,InpLondonEnd))   return InpClrLondon;
   if(InHourRange(hour,InpAsiaStart,InpAsiaEnd))       return InpClrAsia;
   return InpClrDaily;
}

double VisTop()
{
   double mx=ChartGetDouble(0,CHART_PRICE_MAX);
   double mn=ChartGetDouble(0,CHART_PRICE_MIN);
   if(mx<=mn || mx<=0)
      return SymbolInfoDouble(_Symbol,SYMBOL_BID)+8.0;
   return mx-(mx-mn)*0.05;
}

void VisibleBand(double &lo,double &hi)
{
   double mn=ChartGetDouble(0,CHART_PRICE_MIN);
   double mx=ChartGetDouble(0,CHART_PRICE_MAX);
   if(mx<=mn || mx<=0)
   {
      double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
      lo=bid-40.0; hi=bid+40.0;
      return;
   }
   double pad=MathMax(3.0,(mx-mn)*0.20);
   lo=mn-pad;
   hi=mx+pad;
}

string SideTxt(const int d)
{
   if(d>0) return "BUY";
   if(d<0) return "SELL";
   return "FLAT";
}

datetime PhMidnight(const datetime ph)
{
   MqlDateTime t; TimeToStruct(ph,t);
   t.hour=0; t.min=0; t.sec=0;
   return StructToTime(t);
}

int PhYmd(const datetime ph)
{
   MqlDateTime t; TimeToStruct(ph,t);
   return t.year*10000+t.mon*100+t.day;
}

void WipePrefix()
{
   int total=ObjectsTotal(0,0,-1);
   for(int i=total-1;i>=0;i--)
   {
      string n=ObjectName(0,i,0,-1);
      if(StringFind(n,PREFIX)==0) ObjectDelete(0,n);
   }
}

void WipeKind(const string kind)
{
   string p=PREFIX+kind;
   int total=ObjectsTotal(0,0,-1);
   for(int i=total-1;i>=0;i--)
   {
      string n=ObjectName(0,i,0,-1);
      if(StringFind(n,p)==0) ObjectDelete(0,n);
   }
}

bool Read1(const int handle,const int buf,const int shift,double &v)
{
   if(handle==INVALID_HANDLE || shift<0) return false;
   double a[1];
   if(CopyBuffer(handle,buf,shift,1,a)!=1) return false;
   v=a[0];
   return (v!=EMPTY_VALUE);
}

int ClosedHtfShift(const ENUM_TIMEFRAMES tf,const datetime t)
{
   int sh=iBarShift(_Symbol,tf,t,false);
   if(sh<0) return -1;
   return sh+1;
}

int HtfSide(const double fast,const double slow)
{
   if(fast>slow) return 1;
   if(fast<slow) return -1;
   return 0;
}

void StyleBox(const string name,const datetime t1,const datetime t2,
              const double lo,const double hi,const color clr,const int alpha)
{
   if(ObjectFind(0,name)<0)
      ObjectCreate(0,name,OBJ_RECTANGLE,0,t1,hi,t2,lo);
   ObjectMove(0,name,0,t1,hi);
   ObjectMove(0,name,1,t2,lo);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetInteger(0,name,OBJPROP_STYLE,STYLE_SOLID);
   ObjectSetInteger(0,name,OBJPROP_WIDTH,1);
   ObjectSetInteger(0,name,OBJPROP_FILL,true);
   ObjectSetInteger(0,name,OBJPROP_BACK,true);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
   uchar a=(uchar)alpha;
   if(a<10) a=10;
   if(a>120) a=120;
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,(long)ColorToARGB(clr,a));
}

void StyleVLine(const string name,const datetime t,const color clr,const ENUM_LINE_STYLE st)
{
   if(ObjectFind(0,name)<0)
      ObjectCreate(0,name,OBJ_VLINE,0,t,0);
   ObjectSetInteger(0,name,OBJPROP_TIME,t);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetInteger(0,name,OBJPROP_STYLE,st);
   ObjectSetInteger(0,name,OBJPROP_WIDTH,1);
   ObjectSetInteger(0,name,OBJPROP_BACK,true);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}

void StyleSessionName(const string name,const datetime t,const string text,const color bandClr)
{
   double y=VisTop();
   if(ObjectFind(0,name)<0)
      ObjectCreate(0,name,OBJ_TEXT,0,t,y);
   ObjectMove(0,name,0,t,y);
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,13);
   ObjectSetString(0,name,OBJPROP_FONT,"Arial");
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,false);
   ObjectSetInteger(0,name,OBJPROP_BACK,false);
   if(bandClr==clrNONE)
      ObjectSetInteger(0,name,OBJPROP_COLOR,clrYellow);
}

double HourRowY()
{
   double mx=ChartGetDouble(0,CHART_PRICE_MAX);
   double mn=ChartGetDouble(0,CHART_PRICE_MIN);
   if(mx<=mn || mx<=0)
      return SymbolInfoDouble(_Symbol,SYMBOL_BID)+6.0;
   return mx-(mx-mn)*0.08;
}

void StyleHourOnCandle(const string name,const datetime t,const double price,
                       const string text)
{
   if(ObjectFind(0,name)<0)
      ObjectCreate(0,name,OBJ_TEXT,0,t,price);
   ObjectMove(0,name,0,t,price);
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrYellow);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,InpHourFontSize);
   ObjectSetString(0,name,OBJPROP_FONT,"Arial");
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_UPPER);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,false);
   ObjectSetInteger(0,name,OBJPROP_BACK,false);
}

void StyleTag(const string name,const datetime t,const string text,const color clr)
{
   StyleSessionName(name,t,text,clr);
}

void DrawSessionSpan(const string key,const datetime ph0,const int startH,const int endH,
                     const double lo,const double hi,const color clr,const string label,const bool vline)
{
   datetime a=ph0+startH*3600;
   datetime b;
   if(endH==0 && startH>0)
      b=ph0+24*3600;
   else if(startH<endH)
      b=ph0+endH*3600;
   else
      b=ph0+24*3600+endH*3600;

   datetime t1=PhToBroker(a);
   datetime t2=PhToBroker(b);
   if(t2<=t1) t2=t1+60;
   StyleBox(PREFIX+"Z_"+key,t1,t2,lo,hi,clr,InpZoneAlpha);
   int nameShift=(int)((t2-t1)/10);
   if(nameShift<180) nameShift=180;
   StyleSessionName(PREFIX+"T_"+key,t1+(datetime)nameShift,label,clr);
   if(vline && InpDrawOpenLines)
      StyleVLine(PREFIX+"L_"+key,t1,clr,STYLE_DASH);
}

void RedrawSessions(const double lo,const double hi)
{
   if(!InpDrawSessions && !InpDrawDaily) return;
   datetime phNow=BrokerToPh(TimeCurrent());
   datetime today0=PhMidnight(phNow);

   for(int d=0; d<InpDaysBack; d++)
   {
      datetime day0=today0-(datetime)d*86400;
      MqlDateTime dt; TimeToStruct(day0,dt);
      string ymd=StringFormat("%04d%02d%02d",dt.year,dt.mon,dt.day);

      if(InpDrawDaily)
      {
         datetime t1=PhToBroker(day0);
         datetime t2=PhToBroker(day0+24*3600-1);
         StyleBox(PREFIX+"Z_DAY_"+ymd,t1,t2,lo,hi,InpClrDaily,28);
         if(InpDrawOpenLines)
         {
            StyleVLine(PREFIX+"L_DAY_"+ymd,t1,clrWhite,STYLE_SOLID);
            ObjectSetInteger(0,PREFIX+"L_DAY_"+ymd,OBJPROP_WIDTH,2);
         }
         StyleTag(PREFIX+"T_DAY_"+ymd,t1+(datetime)900,
                  StringFormat("%04d-%02d-%02d",dt.year,dt.mon,dt.day),clrWhite);
      }

      if(!InpDrawSessions) continue;

      DrawSessionSpan(ymd+"_ASIA",day0,InpAsiaStart,InpAsiaEnd,lo,hi,InpClrAsia,"ASIAN",true);
      DrawSessionSpan(ymd+"_LON",day0,InpLondonStart,InpLondonEnd,lo,hi,InpClrLondon,"LONDON",true);
      DrawSessionSpan(ymd+"_NY",day0,InpNyStart,InpNyEnd,lo,hi,InpClrNy,"NEW YORK",true);
      DrawSessionSpan(ymd+"_OVLP",day0,InpOverlapStart,InpOverlapEnd,
                      lo+(hi-lo)*0.02,hi-(hi-lo)*0.02,InpClrOverlap,"OVERLAP",true);
   }
}

void DrawPhHourLabels(const datetime &time[],const int rates_total)
{
   WipeKind("HR_");
   WipeKind("HL_");
   if(!InpDrawPhHours || rates_total<10) return;

   datetime phNow=BrokerToPh(TimeCurrent());
   datetime startPh=PhMidnight(phNow)-(datetime)InpDaysBack*86400;
   datetime startBr=PhToBroker(startPh);

   int firstVis=(int)ChartGetInteger(0,CHART_FIRST_VISIBLE_BAR);
   int visBars=(int)ChartGetInteger(0,CHART_VISIBLE_BARS);
   datetime visLeft=0,visRight=0;
   if(firstVis>=0 && visBars>0)
   {
      visLeft=iTime(_Symbol,_Period,firstVis);
      int rightSh=firstVis-visBars+1;
      if(rightSh<0) rightSh=0;
      visRight=iTime(_Symbol,_Period,rightSh);
   }

   int i0=0;
   for(int i=0;i<rates_total;i++)
   {
      if(time[i]>=startBr) { i0=i; break; }
   }

   double y=HourRowY();
   int lastH=-1;
   int lastYmd=-1;
   for(int i=i0;i<rates_total;i++)
   {
      if(visLeft>0 && visRight>0)
      {
         if(time[i]<visLeft-3600 || time[i]>visRight+3600) continue;
      }
      datetime ph=BrokerToPh(time[i]);
      MqlDateTime t; TimeToStruct(ph,t);
      int ymd=t.year*10000+t.mon*100+t.day;
      if(t.hour==lastH && ymd==lastYmd) continue;
      lastH=t.hour;
      lastYmd=ymd;

      string key=StringFormat("%d_%02d",ymd,t.hour);
      color clr=SessionColor(t.hour);
      StyleHourOnCandle(PREFIX+"HR_"+key,time[i],y,FormatPhHour(t.hour));
      if(InpDrawHourLines)
      {
         StyleVLine(PREFIX+"HL_"+key,time[i],clr,STYLE_DOT);
         ObjectSetInteger(0,PREFIX+"HL_"+key,OBJPROP_WIDTH,1);
      }
   }
}

void RelayoutNames()
{
   double y=VisTop();
   int total=ObjectsTotal(0,0,-1);
   for(int i=total-1;i>=0;i--)
   {
      string n=ObjectName(0,i,0,-1);
      if(StringFind(n,PREFIX+"T_")!=0) continue;
      datetime t=(datetime)ObjectGetInteger(0,n,OBJPROP_TIME);
      ObjectMove(0,n,0,t,y);
   }
}

void RelayoutHours()
{
   double y=HourRowY();
   int total=ObjectsTotal(0,0,-1);
   for(int i=total-1;i>=0;i--)
   {
      string n=ObjectName(0,i,0,-1);
      if(StringFind(n,PREFIX+"HR_")!=0) continue;
      datetime t=(datetime)ObjectGetInteger(0,n,OBJPROP_TIME);
      ObjectMove(0,n,0,t,y);
   }
}

void RefreshHourLabels()
{
   if(!InpDrawPhHours) return;
   datetime t[];
   ArraySetAsSeries(t,false);
   int n=CopyTime(_Symbol,_Period,0,2500,t);
   if(n<=1) return;
   DrawPhHourLabels(t,n);
}

void MarkSignal(const datetime t,const double price,const int dir)
{
   string n=PREFIX+"SIG_"+TimeToString(t,TIME_DATE|TIME_MINUTES);
   if(ObjectFind(0,n)<0)
      ObjectCreate(0,n,OBJ_TEXT,0,t,price);
   ObjectMove(0,n,0,t,price);
   if(dir>0)
   {
      ObjectSetString(0,n,OBJPROP_TEXT," BUY");
      ObjectSetInteger(0,n,OBJPROP_COLOR,clrLime);
   }
   else
   {
      ObjectSetString(0,n,OBJPROP_TEXT," SELL");
      ObjectSetInteger(0,n,OBJPROP_COLOR,clrRed);
   }
   ObjectSetInteger(0,n,OBJPROP_ANCHOR,ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,11);
   ObjectSetString(0,n,OBJPROP_FONT,"Arial");
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,false);
   ObjectSetInteger(0,n,OBJPROP_BACK,false);
}

double DotY(const double hi,const double lo)
{
   double rng=hi-lo;
   if(rng<0.0) rng=0.0;
   double pad=InpArrowOffsetUsd;
   if(pad<1.0) pad=1.0;
   if(rng>0.0 && rng*0.12>pad) pad=rng*0.12;
   return hi+pad;
}

void MarkWait(const datetime t,const double price,const int dir)
{
   if(!InpShowHourBlockedSetups) return;
   string n=PREFIX+"WAIT_"+TimeToString(t,TIME_DATE|TIME_MINUTES);
   if(ObjectFind(0,n)<0)
      ObjectCreate(0,n,OBJ_TEXT,0,t,price);
   ObjectMove(0,n,0,t,price);
   if(dir>0)
   {
      ObjectSetString(0,n,OBJPROP_TEXT," o");
      ObjectSetInteger(0,n,OBJPROP_COLOR,clrYellow);
   }
   else
   {
      ObjectSetString(0,n,OBJPROP_TEXT," o");
      ObjectSetInteger(0,n,OBJPROP_COLOR,clrOrange);
   }
   ObjectSetInteger(0,n,OBJPROP_ANCHOR,ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,14);
   ObjectSetString(0,n,OBJPROP_FONT,"Arial");
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,false);
   ObjectSetInteger(0,n,OBJPROP_BACK,false);
}

void DrawBiasLabel(const datetime t,const double ema,const string side)
{
   if(!InpShowBiasLine || ema<=0) return;
   string n=PREFIX+"BIASLBL";
   if(ObjectFind(0,n)<0)
      ObjectCreate(0,n,OBJ_TEXT,0,t,ema);
   ObjectMove(0,n,0,t,ema);
   ObjectSetString(0,n,OBJPROP_TEXT," BIAS "+side);
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,10);
   ObjectSetString(0,n,OBJPROP_FONT,"Arial");
   ObjectSetInteger(0,n,OBJPROP_ANCHOR,ANCHOR_LEFT_UPPER);
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,false);
   ObjectSetInteger(0,n,OBJPROP_BACK,false);
   if(side=="BUY")
      ObjectSetInteger(0,n,OBJPROP_COLOR,clrLime);
   else if(side=="SELL")
      ObjectSetInteger(0,n,OBJPROP_COLOR,clrRed);
   else
      ObjectSetInteger(0,n,OBJPROP_COLOR,clrGold);
}

void DrawH4Sr()
{
   if(!InpDrawH4Sr) return;
   int ihi=iHighest(_Symbol,PERIOD_H4,MODE_HIGH,20,1);
   int ilo=iLowest(_Symbol,PERIOD_H4,MODE_LOW,20,1);
   if(ihi<0 || ilo<0) return;
   double hi=iHigh(_Symbol,PERIOD_H4,ihi);
   double lo=iLow(_Symbol,PERIOD_H4,ilo);
   datetime t1=iTime(_Symbol,PERIOD_H4,20);
   datetime t2=TimeCurrent()+PeriodSeconds(PERIOD_H1);
   if(t1<=0 || hi<=0 || lo<=0) return;

   string n1=PREFIX+"H4HI", n2=PREFIX+"H4LO";
   if(ObjectFind(0,n1)<0) ObjectCreate(0,n1,OBJ_TREND,0,t1,hi,t2,hi);
   ObjectMove(0,n1,0,t1,hi); ObjectMove(0,n1,1,t2,hi);
   ObjectSetInteger(0,n1,OBJPROP_COLOR,C'80,180,80');
   ObjectSetInteger(0,n1,OBJPROP_STYLE,STYLE_DOT);
   ObjectSetInteger(0,n1,OBJPROP_RAY_RIGHT,true);
   ObjectSetInteger(0,n1,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n1,OBJPROP_BACK,true);

   if(ObjectFind(0,n2)<0) ObjectCreate(0,n2,OBJ_TREND,0,t1,lo,t2,lo);
   ObjectMove(0,n2,0,t1,lo); ObjectMove(0,n2,1,t2,lo);
   ObjectSetInteger(0,n2,OBJPROP_COLOR,C'200,90,90');
   ObjectSetInteger(0,n2,OBJPROP_STYLE,STYLE_DOT);
   ObjectSetInteger(0,n2,OBJPROP_RAY_RIGHT,true);
   ObjectSetInteger(0,n2,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n2,OBJPROP_BACK,true);
}

void CsvEnsureHeader(const bool rewrite)
{
   if(!InpLogCsv) return;
   int flags=FILE_CSV|FILE_ANSI|FILE_READ|FILE_WRITE|FILE_SHARE_READ|FILE_SHARE_WRITE;
   if(rewrite) flags|=FILE_REWRITE;
   int fh=FileOpen(CSV_NAME,flags);
   if(fh==INVALID_HANDLE) return;
   if(rewrite || FileSize(fh)==0)
   {
      FileSeek(fh,0,SEEK_SET);
      FileWrite(fh,"time_broker","time_ph","ph_clock","session","side","entry",
                "h4","h1","m30","m5bias","adx","gap","rsi","score","reason");
   }
   FileClose(fh);
}

void CsvAppend(const datetime br,const datetime ph,const string clock,const string sess,
               const string side,const double entry,const string h4,const string h1,const string m30,
               const string m5bias,const double adx,const double gap,const double rsi,
               const int score,const string reason)
{
   if(!InpLogCsv) return;
   int fh=FileOpen(CSV_NAME,FILE_CSV|FILE_ANSI|FILE_READ|FILE_WRITE|FILE_SHARE_READ|FILE_SHARE_WRITE);
   if(fh==INVALID_HANDLE) return;
   FileSeek(fh,0,SEEK_END);
   FileWrite(fh,
             TimeToString(br,TIME_DATE|TIME_SECONDS),
             TimeToString(ph,TIME_DATE|TIME_MINUTES),
             clock,sess,side,
             DoubleToString(entry,_Digits),
             h4,h1,m30,m5bias,
             DoubleToString(adx,1),
             DoubleToString(gap,3),
             DoubleToString(rsi,1),
             IntegerToString(score),
             reason);
   FileClose(fh);
}

void PutCard(const int idx,const datetime t,const double price,const string text,const color clr)
{
   if(!InpShowSignalCards) return;
   string name=PREFIX+"CARD_"+IntegerToString(idx);
   if(ObjectFind(0,name)<0)
      ObjectCreate(0,name,OBJ_TEXT,0,t,price);
   ObjectMove(0,name,0,t,price);
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,8);
   ObjectSetString(0,name,OBJPROP_FONT,"Consolas");
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
}

void RefreshCards(const datetime &time[],const double &high[],const double &low[],
                  const double &buy[],const double &sell[],const int rates_total)
{
   if(!InpShowSignalCards) return;
   for(int k=0;k<InpMaxLabels;k++)
      ObjectDelete(0,PREFIX+"CARD_"+IntegerToString(k));

   int found=0;
   for(int i=rates_total-2;i>=1 && found<InpMaxLabels;i--)
   {
      bool isBuy=(buy[i]!=EMPTY_VALUE && buy[i]>0);
      bool isSell=(sell[i]!=EMPTY_VALUE && sell[i]>0);
      if(!isBuy && !isSell) continue;

      datetime ph=BrokerToPh(time[i]);
      MqlDateTime tm; TimeToStruct(ph,tm);
      string sess=SessionName(tm.hour);
      bool buySide=isBuy;
      string arrow=buySide?"BUY ^":"SELL v";
      double entry=buySide?buy[i]+InpArrowOffsetUsd:sell[i]-InpArrowOffsetUsd;

      int shH1=ClosedHtfShift(PERIOD_H1,time[i]);
      int shM30=ClosedHtfShift(PERIOD_M30,time[i]);
      double h1f=0,h1s=0,m30f=0,m30s=0;
      string h1="FLAT", m30="FLAT";
      if(Read1(hH1F,0,shH1,h1f) && Read1(hH1S,0,shH1,h1s)) h1=SideTxt(HtfSide(h1f,h1s));
      if(Read1(hM30F,0,shM30,m30f) && Read1(hM30S,0,shM30,m30s)) m30=SideTxt(HtfSide(m30f,m30s));

      string card=StringFormat("%s\nPH TIME: %s\nSESSION: %s\nH1 TREND: %s\nM30 TREND: %s\nENTRY: %s",
                               arrow,FormatPhClock(ph),sess,h1,m30,DoubleToString(entry,_Digits));
      double px=buySide?low[i]-InpArrowOffsetUsd*3.0:high[i]+InpArrowOffsetUsd*1.2;
      PutCard(found,time[i],px,card,buySide?clrLime:clrTomato);
      found++;
   }
}

bool V640ProfitHourAllowed(const int dir,const int hour)
{
   if(hour==4  && dir<0) return true;
   if(hour==5)           return true;
   if(hour==8)           return true;
   if(hour==11 && dir<0) return true;
   if(hour==12 && dir<0) return true;
   if(hour==17 && dir>0) return true;
   if(hour==19 && dir>0) return true;
   if(hour==21 && dir<0) return true;
   if(hour==22 && dir>0) return true;
   return false;
}

bool HybridHourDirectionAllowed(const int dir,const int hour)
{
   if(hour==5 || hour==8) return true;
   if(hour==21 && dir<0) return true;
   if(hour==23 && dir>0) return true;
   return false;
}

bool HourDirectionAllowed(const int dir,const int hour)
{
   if(InpUseV640ProfitHourRouter)
      return V640ProfitHourAllowed(dir,hour);
   if(!InpBest4HoursOnly) return true;
   return HybridHourDirectionAllowed(dir,hour);
}

int FlowScore(const int bias,const int flow,const double adx,const double gapATR,
              const double rsi,const double bodyRatio,const double rangeAtr)
{
   int score=0;
   if(flow==bias) score++;
   if(adx>=InpWeakADXLevel) score++;
   if(gapATR>=InpMinM5GapATR) score++;
   if(rangeAtr>=0.25 && rangeAtr<=0.65) score++;
   if(bias>0)
   {
      if(rsi>=48.0 && rsi<=64.0) score++;
   }
   else
   {
      if(rsi>=36.0 && rsi<=52.0) score++;
   }
   if(bodyRatio>=0.12 && bodyRatio<=0.40) score++;
   return score;
}

int M5BiasFrom(const double fast,const double slow,const double adx,const double m5atr,double &gapATR)
{
   gapATR=0.0;
   if(m5atr<=0.0) return 0;
   gapATR=MathAbs(fast-slow)/m5atr;
   if(adx<InpMinADX) return 0;
   if(InpUseChopFilter && gapATR<InpMinM5GapATR && adx<InpWeakADXLevel)
      return 0;
   if(fast>slow) return 1;
   if(fast<slow) return -1;
   return 0;
}

bool ScalperBlocks(const int bias,const double adx,const double gapATR)
{
   if(InpBlockMidADX && adx>=InpBlockADXFrom && adx<InpBlockADXTo) return true;
   if(InpV641BlockSellADX20To25 && bias<0 &&
      adx>=InpV641SellADXBlockFrom && adx<InpV641SellADXBlockTo) return true;
   if(InpV642BlockBuyGap050To100 && bias>0 &&
      gapATR>=InpV642BuyGapBlockFrom && gapATR<InpV642BuyGapBlockTo) return true;
   if(InpV643BlockSellGap075To100 && bias<0 &&
      gapATR>=InpV643SellGapBlockFrom && gapATR<InpV643SellGapBlockTo) return true;
   if(InpBlockBuyWeakEmaGap && bias>0 && gapATR<InpBuyWeakGapATR) return true;
   return false;
}

bool IsSmallCandle(const double bodyRatio,const double rangeAtr)
{
   return (rangeAtr>=InpMinSmallRangeATR && rangeAtr<=InpMaxSmallRangeATR &&
           bodyRatio<=InpSmallBodyRatioMax);
}

bool ClosedM1Breakout(const int bias,const double smallHigh,const double smallLow,
                      const double brkHigh,const double brkLow,const double atr)
{
   if(atr<=0.0) return false;
   double buffer=atr*InpBreakBufferATR;
   if(bias>0) return (brkHigh > smallHigh + buffer);
   if(bias<0) return (brkLow < smallLow - buffer);
   return false;
}

bool TryScalperAtM1(const MqlRates &small,const MqlRates &brk,
                    int &dirOut,string &reasonOut,
                    string &h4s,string &h1s,string &m30s,string &biasS,
                    double &rsiV,double &adxV,double &gapV,int &scoreV,
                    int &gradeOut)
{
   dirOut=0;
   reasonOut="";
   h4s="FLAT"; h1s="FLAT"; m30s="FLAT"; biasS="FLAT";
   rsiV=0; adxV=0; gapV=0; scoreV=0;
   gradeOut=0;

   int s5=ClosedHtfShift(PERIOD_M5,brk.time);
   double fast=0,slow=0,adx=0,m5atr=0;
   if(!Read1(hM5Fast,0,s5,fast) || !Read1(hM5Slow,0,s5,slow) ||
      !Read1(hM5ADX,0,s5,adx) || !Read1(hM5ATR,0,s5,m5atr))
      return false;

   double gapATR=0.0;
   int bias=M5BiasFrom(fast,slow,adx,m5atr,gapATR);
   adxV=adx;
   gapV=gapATR;
   if(bias==0) return false;
   if(ScalperBlocks(bias,adx,gapATR)) return false;
   biasS=SideTxt(bias);

   int s1=iBarShift(_Symbol,PERIOD_M1,small.time,false);
   double atr=0,m1f=0,m1s=0,rsi=0;
   if(!Read1(hM1ATR,0,s1,atr) || atr<=0.0) return false;
   if(!Read1(hM1Fast,0,s1,m1f) || !Read1(hM1Slow,0,s1,m1s) || !Read1(hM1RSI,0,s1,rsi))
      return false;
   rsiV=rsi;

   double range=small.high-small.low;
   if(range<=0.0) return false;
   double bodyRatio=MathAbs(small.close-small.open)/range;
   double rangeAtr=range/atr;
   if(!IsSmallCandle(bodyRatio,rangeAtr)) return false;

   int flow=HtfSide(m1f,m1s);
   if(InpRequireM1Flow && flow!=bias) return false;

   int score=FlowScore(bias,flow,adx,gapATR,rsi,bodyRatio,rangeAtr);
   scoreV=score;
   if(InpUseFlowScore && score<InpMinFlowScore) return false;

   if(bias>0)
   {
      if(rsi<InpBuyRSIMin || rsi>InpBuyRSIMax) return false;
   }
   else
   {
      if(rsi<InpSellRSIMin || rsi>InpSellRSIMax) return false;
   }

   int shH4=ClosedHtfShift(PERIOD_H4,brk.time);
   int shH1=ClosedHtfShift(PERIOD_H1,brk.time);
   int shM30=ClosedHtfShift(PERIOD_M30,brk.time);
   double h4f=0,h4w=0,h1f=0,h1w=0,m30f=0,m30w=0;
   if(Read1(hH4F,0,shH4,h4f) && Read1(hH4S,0,shH4,h4w)) h4s=SideTxt(HtfSide(h4f,h4w));
   if(Read1(hH1F,0,shH1,h1f) && Read1(hH1S,0,shH1,h1w)) h1s=SideTxt(HtfSide(h1f,h1w));
   if(Read1(hM30F,0,shM30,m30f) && Read1(hM30S,0,shM30,m30w)) m30s=SideTxt(HtfSide(m30f,m30s));

   string sTxt=SideTxt(bias);
   if(InpRequireH1 && h1s!=sTxt) return false;
   if(InpRequireM30 && m30s!=sTxt) return false;
   if(InpRequireH4 && h4s!=sTxt) return false;

   if(!ClosedM1Breakout(bias,small.high,small.low,brk.high,brk.low,atr))
      return false;

   MqlDateTime tm; TimeToStruct(brk.time,tm);
   bool hourOk=HourDirectionAllowed(bias,tm.hour);
   datetime ph=BrokerToPh(brk.time);
   string clock=FormatPhClock(ph);
   MqlDateTime pht; TimeToStruct(ph,pht);
   string sess=SessionName(pht.hour);
   reasonOut=StringFormat(
      "SIDE=%s|PH=%s|SESSION=%s|ENTRY=%.2f|H4=%s|H1=%s|M30=%s|M5=%s|ADX=%.1f|GAP=%.3f|RSI=%.1f|SCORE=%d|V640=%s|HOUR=%s|SMALL+BREAK",
      sTxt,clock,sess,brk.close,h4s,h1s,m30s,biasS,adx,gapATR,rsi,score,
      (InpUseV640ProfitHourRouter?"ON":"off"),
      (hourOk?"OK":"BLOCK"));
   dirOut=bias;
   gradeOut=(hourOk ? 1 : 2);
   return true;
}

bool TryScalperM5Fallback(const datetime smallT,const double sO,const double sH,
                          const double sL,const double sC,
                          const datetime brkT,const double bH,const double bL,const double bC,
                          int &dirOut,string &reasonOut,
                          string &h4s,string &h1s,string &m30s,string &biasS,
                          double &rsiV,double &adxV,double &gapV,int &scoreV,
                          int &gradeOut)
{
   dirOut=0; gradeOut=0;
   reasonOut="";
   h4s="FLAT"; h1s="FLAT"; m30s="FLAT"; biasS="FLAT";
   rsiV=0; adxV=0; gapV=0; scoreV=0;

   int s5=ClosedHtfShift(PERIOD_M5,brkT);
   double fast=0,slow=0,adx=0,m5atr=0;
   if(!Read1(hM5Fast,0,s5,fast) || !Read1(hM5Slow,0,s5,slow) ||
      !Read1(hM5ADX,0,s5,adx) || !Read1(hM5ATR,0,s5,m5atr))
      return false;
   double gapATR=0.0;
   int bias=M5BiasFrom(fast,slow,adx,m5atr,gapATR);
   if(bias==0) return false;
   if(ScalperBlocks(bias,adx,gapATR)) return false;

   int shSmall=iBarShift(_Symbol,PERIOD_M5,smallT,false);
   double atr=0;
   if(!Read1(hM5ATR,0,shSmall,atr) || atr<=0.0) return false;
   double range=sH-sL;
   if(range<=0.0) return false;
   double bodyRatio=MathAbs(sC-sO)/range;
   double rangeAtr=range/atr;
   if(!IsSmallCandle(bodyRatio,rangeAtr)) return false;

   int s1=ClosedHtfShift(PERIOD_M1,smallT);
   double m1f=0,m1s=0,rsi=0;
   if(!Read1(hM1Fast,0,s1,m1f) || !Read1(hM1Slow,0,s1,m1s) || !Read1(hM1RSI,0,s1,rsi))
      return false;
   int flow=HtfSide(m1f,m1s);
   if(InpRequireM1Flow && flow!=bias) return false;
   int score=FlowScore(bias,flow,adx,gapATR,rsi,bodyRatio,rangeAtr);
   if(InpUseFlowScore && score<InpMinFlowScore) return false;
   if(bias>0) { if(rsi<InpBuyRSIMin || rsi>InpBuyRSIMax) return false; }
   else { if(rsi<InpSellRSIMin || rsi>InpSellRSIMax) return false; }

   int shH4=ClosedHtfShift(PERIOD_H4,brkT);
   int shH1=ClosedHtfShift(PERIOD_H1,brkT);
   int shM30=ClosedHtfShift(PERIOD_M30,brkT);
   double h4f=0,h4w=0,h1f=0,h1w=0,m30f=0,m30w=0;
   if(Read1(hH4F,0,shH4,h4f) && Read1(hH4S,0,shH4,h4w)) h4s=SideTxt(HtfSide(h4f,h4w));
   if(Read1(hH1F,0,shH1,h1f) && Read1(hH1S,0,shH1,h1w)) h1s=SideTxt(HtfSide(h1f,h1w));
   if(Read1(hM30F,0,shM30,m30f) && Read1(hM30S,0,shM30,m30w)) m30s=SideTxt(HtfSide(m30f,m30s));
   string sTxt=SideTxt(bias);
   if(InpRequireH1 && h1s!=sTxt) return false;
   if(InpRequireM30 && m30s!=sTxt) return false;
   if(InpRequireH4 && h4s!=sTxt) return false;
   if(!ClosedM1Breakout(bias,sH,sL,bH,bL,atr)) return false;

   MqlDateTime tm; TimeToStruct(brkT,tm);
   bool hourOk=HourDirectionAllowed(bias,tm.hour);
   datetime ph=BrokerToPh(brkT);
   string clock=FormatPhClock(ph);
   MqlDateTime pht; TimeToStruct(ph,pht);
   reasonOut=StringFormat(
      "SIDE=%s|PH=%s|SESSION=%s|ENTRY=%.2f|H4=%s|H1=%s|M30=%s|M5=%s|ADX=%.1f|GAP=%.3f|RSI=%.1f|SCORE=%d|V640=%s|HOUR=%s|M5FALLBACK",
      sTxt,clock,SessionName(pht.hour),bC,h4s,h1s,m30s,sTxt,adx,gapATR,rsi,score,
      (InpUseV640ProfitHourRouter?"ON":"off"),
      (hourOk?"OK":"BLOCK"));
   dirOut=bias; biasS=sTxt; rsiV=rsi; adxV=adx; gapV=gapATR; scoreV=score;
   gradeOut=(hourOk ? 1 : 2);
   return true;
}

bool EvalBar(const int i,const datetime &time[],
             const double &open[],const double &high[],
             const double &low[],const double &close[],
             const int rates_total,const MqlRates &m1[],const int nM1,
             int &dirOut,string &reasonOut,
             string &h4s,string &h1s,string &m30s,string &biasS,
             double &rsiV,double &adxV,double &gapV,int &scoreV,int &gradeOut)
{
   dirOut=0;
   reasonOut="";
   h4s="FLAT"; h1s="FLAT"; m30s="FLAT"; biasS="FLAT";
   rsiV=0; adxV=0; gapV=0; scoreV=0;
   gradeOut=0;

   datetime t0=time[i];
   datetime t1=(i+1<rates_total ? time[i+1] : t0+(datetime)PeriodSeconds(_Period));

   int waitDir=0;
   string waitReason,waitH4,waitH1,waitM30,waitBias;
   double waitRsi=0,waitAdx=0,waitGap=0;
   int waitScore=0;

   for(int k=1;k<nM1;k++)
   {
      if(m1[k].time>=t1) break;
      if(m1[k].time<t0) continue;
      int g=0,d=0,sc=0;
      string rs,hh4,hh1,hm30,bs;
      double rv=0,av=0,gv=0;
      if(!TryScalperAtM1(m1[k-1],m1[k],d,rs,hh4,hh1,hm30,bs,rv,av,gv,sc,g))
         continue;
      if(g==1)
      {
         dirOut=d; reasonOut=rs; h4s=hh4; h1s=hh1; m30s=hm30; biasS=bs;
         rsiV=rv; adxV=av; gapV=gv; scoreV=sc; gradeOut=1;
         return true;
      }
      if(g==2 && waitDir==0)
      {
         waitDir=d; waitReason=rs; waitH4=hh4; waitH1=hh1; waitM30=hm30; waitBias=bs;
         waitRsi=rv; waitAdx=av; waitGap=gv; waitScore=sc;
      }
   }

   if(i>=1)
   {
      int g=0,d=0,sc=0;
      string rs,hh4,hh1,hm30,bs;
      double rv=0,av=0,gv=0;
      if(TryScalperM5Fallback(time[i-1],open[i-1],high[i-1],low[i-1],close[i-1],
                              time[i],high[i],low[i],close[i],
                              d,rs,hh4,hh1,hm30,bs,rv,av,gv,sc,g))
      {
         if(g==1)
         {
            dirOut=d; reasonOut=rs; h4s=hh4; h1s=hh1; m30s=hm30; biasS=bs;
            rsiV=rv; adxV=av; gapV=gv; scoreV=sc; gradeOut=1;
            return true;
         }
         if(g==2 && waitDir==0)
         {
            waitDir=d; waitReason=rs; waitH4=hh4; waitH1=hh1; waitM30=hm30; waitBias=bs;
            waitRsi=rv; waitAdx=av; waitGap=gv; waitScore=sc;
         }
      }
   }

   if(waitDir==0) return false;
   dirOut=waitDir; reasonOut=waitReason; h4s=waitH4; h1s=waitH1; m30s=waitM30; biasS=waitBias;
   rsiV=waitRsi; adxV=waitAdx; gapV=waitGap; scoreV=waitScore; gradeOut=2;
   return true;
}

bool FeedsReady()
{
   if(BarsCalculated(hM5Fast)<60 || BarsCalculated(hM5Slow)<60 ||
      BarsCalculated(hM5ADX)<60 || BarsCalculated(hM5ATR)<60)
      return false;
   if(BarsCalculated(hM1ATR)<60 || BarsCalculated(hM1RSI)<60 ||
      BarsCalculated(hM1Fast)<60)
      return false;
   if(BarsCalculated(hH1F)<20 || BarsCalculated(hM30F)<20)
      return false;
   g_m1Bars=Bars(_Symbol,PERIOD_M1);
   if(g_m1Bars<200)
   {
      MqlRates tmp[];
      CopyRates(_Symbol,PERIOD_M1,0,4000,tmp);
      CopyRates(_Symbol,PERIOD_M30,0,500,tmp);
      CopyRates(_Symbol,PERIOD_H1,0,400,tmp);
      return false;
   }
   return true;
}

void ReadHtfPanel(const datetime t,string &h4s,string &h1s,string &m30s,string &biasS,
                  double &adxV,double &gapV,double &rsiV,double &slowEma,double &fastEma)
{
   h4s="FLAT"; h1s="FLAT"; m30s="FLAT"; biasS="FLAT";
   adxV=0; gapV=0; rsiV=0; slowEma=0; fastEma=0;
   int s5=ClosedHtfShift(PERIOD_M5,t);
   double f=0,s=0,adx=0,atr=0;
   if(Read1(hM5Fast,0,s5,f) && Read1(hM5Slow,0,s5,s) &&
      Read1(hM5ADX,0,s5,adx) && Read1(hM5ATR,0,s5,atr))
   {
      fastEma=f; slowEma=s; adxV=adx;
      biasS=SideTxt(M5BiasFrom(f,s,adx,atr,gapV));
   }
   int s1=ClosedHtfShift(PERIOD_M1,t);
   Read1(hM1RSI,0,s1,rsiV);
   int shH4=ClosedHtfShift(PERIOD_H4,t);
   int shH1=ClosedHtfShift(PERIOD_H1,t);
   int shM30=ClosedHtfShift(PERIOD_M30,t);
   double h4f=0,h4w=0,h1f=0,h1w=0,m30f=0,m30w=0;
   if(Read1(hH4F,0,shH4,h4f) && Read1(hH4S,0,shH4,h4w)) h4s=SideTxt(HtfSide(h4f,h4w));
   if(Read1(hH1F,0,shH1,h1f) && Read1(hH1S,0,shH1,h1w)) h1s=SideTxt(HtfSide(h1f,h1w));
   if(Read1(hM30F,0,shM30,m30f) && Read1(hM30S,0,shM30,m30w)) m30s=SideTxt(HtfSide(m30f,m30w));
}

void Panel(const double close,const string biasS,const double adx,const double gap,
           const double rsi,const string h4,const string h1,const string m30)
{
   if(!InpShowPanel) return;
   datetime ph=BrokerToPh(TimeCurrent());
   MqlDateTime tm; TimeToStruct(ph,tm);
   string sess=SessionName(tm.hour);
   MqlDateTime br; TimeToStruct(TimeCurrent(),br);
   bool v640Buy=V640ProfitHourAllowed(1,br.hour);
   bool v640Sell=V640ProfitHourAllowed(-1,br.hour);
   string v640;
   if(!InpUseV640ProfitHourRouter) v640="V640 OFF";
   else if(v640Buy && v640Sell) v640="V640 BUY+SELL ON";
   else if(v640Buy) v640="V640 BUY ON";
   else if(v640Sell) v640="V640 SELL ON";
   else v640="V640 both OFF";

   Comment("JM GOLD SESSION SIGNAL v1.31  |  VISUAL ONLY - walang order\n",
           "PH TIME  ",FormatPhClock(ph),
           StringFormat("   %04d-%02d-%02d",tm.year,tm.mon,tm.day),
           "   SESSION: ",sess,"\n",
           "ENTRY: maliit na DOT + BUY/SELL sa TAAS ng candle (lime BUY / red SELL)\n",
           "Yellow/orange o = strategy OK pero V640 hour OFF. LAST: ",
           (g_lastSide==""?"none yet":g_lastSide+" at "+g_lastClock+" PH"),
           StringFormat("  |  dots=%d  hour-block=%d",g_signalCount,g_waitCount),"\n",
           "Flow: V6.77 M5 EMA+ADX+gap  +  small-candle break  +  M1 flow/RSI/score>=3\n",
           "Mix: H1 required  |  M30 required  |  H4 display  |  ",v640,"\n",
           "H4: ",h4,"   H1: ",h1,"   M30: ",m30,"   M5 BIAS: ",biasS,"\n",
           "CHART ",EnumToString(_Period),
           "  ADX ",DoubleToString(adx,1),
           "  GapATR ",DoubleToString(gap,3),
           "  RSI ",DoubleToString(rsi,1),
           "  close ",DoubleToString(close,_Digits),
           "  M1 bars ",IntegerToString(g_m1Bars),"\n",
           "Filters  H1=",(InpRequireH1?"ON":"off"),
           " M30=",(InpRequireM30?"ON":"off"),
           " H4=",(InpRequireH4?"ON":"off"),
           " V640=",(InpUseV640ProfitHourRouter?"ON":"off"),
           " score>=",IntegerToString(InpMinFlowScore),"\n",
           "CSV  MQL5\\Files\\",CSV_NAME,"\n",
           (g_lastReason==""?"Last signal: none yet":"Last: "+g_lastReason),"\n",
           "Broker H",IntegerToString(br.hour),"  (offset vs GMT ",IntegerToString(g_gmtOff/3600),"h)");
}

int OnInit()
{
   SetIndexBuffer(0,BufBuy,INDICATOR_DATA);
   SetIndexBuffer(1,BufSell,INDICATOR_DATA);
   SetIndexBuffer(2,BufBias,INDICATOR_DATA);
   SetIndexBuffer(3,BufFast,INDICATOR_DATA);
   PlotIndexSetInteger(0,PLOT_ARROW,DOT_CODE);
   PlotIndexSetInteger(1,PLOT_ARROW,DOT_CODE);
   PlotIndexSetDouble(0,PLOT_EMPTY_VALUE,EMPTY_VALUE);
   PlotIndexSetDouble(1,PLOT_EMPTY_VALUE,EMPTY_VALUE);
   PlotIndexSetDouble(2,PLOT_EMPTY_VALUE,EMPTY_VALUE);
   PlotIndexSetDouble(3,PLOT_EMPTY_VALUE,EMPTY_VALUE);
   ArraySetAsSeries(BufBuy,false);
   ArraySetAsSeries(BufSell,false);
   ArraySetAsSeries(BufBias,false);
   ArraySetAsSeries(BufFast,false);
   PlotIndexSetInteger(0,PLOT_LINE_WIDTH,3);
   PlotIndexSetInteger(1,PLOT_LINE_WIDTH,3);
   PlotIndexSetInteger(2,PLOT_LINE_WIDTH,2);
   PlotIndexSetInteger(3,PLOT_LINE_WIDTH,1);
   ChartSetInteger(0,CHART_FOREGROUND,false);
   ChartRedraw(0);

   hM5Fast=iMA(_Symbol,PERIOD_M5,InpM5FastEMA,0,MODE_EMA,PRICE_CLOSE);
   hM5Slow=iMA(_Symbol,PERIOD_M5,InpM5SlowEMA,0,MODE_EMA,PRICE_CLOSE);
   hM5ADX=iADX(_Symbol,PERIOD_M5,InpM5ADXPeriod);
   hM5ATR=iATR(_Symbol,PERIOD_M5,14);
   hM1Fast=iMA(_Symbol,PERIOD_M1,InpM1FastEMA,0,MODE_EMA,PRICE_CLOSE);
   hM1Slow=iMA(_Symbol,PERIOD_M1,InpM1SlowEMA,0,MODE_EMA,PRICE_CLOSE);
   hM1RSI=iRSI(_Symbol,PERIOD_M1,InpM1RSIPeriod,PRICE_CLOSE);
   hM1ATR=iATR(_Symbol,PERIOD_M1,InpM1ATRPeriod);
   hH1F=iMA(_Symbol,PERIOD_H1,InpH1Fast,0,MODE_EMA,PRICE_CLOSE);
   hH1S=iMA(_Symbol,PERIOD_H1,InpH1Slow,0,MODE_EMA,PRICE_CLOSE);
   hH4F=iMA(_Symbol,PERIOD_H4,InpH4Fast,0,MODE_EMA,PRICE_CLOSE);
   hH4S=iMA(_Symbol,PERIOD_H4,InpH4Slow,0,MODE_EMA,PRICE_CLOSE);
   hM30F=iMA(_Symbol,PERIOD_M30,InpM30Fast,0,MODE_EMA,PRICE_CLOSE);
   hM30S=iMA(_Symbol,PERIOD_M30,InpM30Slow,0,MODE_EMA,PRICE_CLOSE);

   if(hM5Fast==INVALID_HANDLE || hM5Slow==INVALID_HANDLE || hM5ADX==INVALID_HANDLE ||
      hM5ATR==INVALID_HANDLE || hM1Fast==INVALID_HANDLE || hM1Slow==INVALID_HANDLE ||
      hM1RSI==INVALID_HANDLE || hM1ATR==INVALID_HANDLE ||
      hH1F==INVALID_HANDLE || hH1S==INVALID_HANDLE ||
      hH4F==INVALID_HANDLE || hH4S==INVALID_HANDLE ||
      hM30F==INVALID_HANDLE || hM30S==INVALID_HANDLE)
      return INIT_FAILED;

   g_gmtOff=BrokerGmtOff();
   MqlRates wr[];
   CopyRates(_Symbol,PERIOD_M1,0,4000,wr);
   CopyRates(_Symbol,PERIOD_M30,0,500,wr);
   CopyRates(_Symbol,PERIOD_H1,0,400,wr);
   CopyRates(_Symbol,PERIOD_H4,0,200,wr);
   CsvEnsureHeader(true);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hM5Fast!=INVALID_HANDLE) IndicatorRelease(hM5Fast);
   if(hM5Slow!=INVALID_HANDLE) IndicatorRelease(hM5Slow);
   if(hM5ADX!=INVALID_HANDLE) IndicatorRelease(hM5ADX);
   if(hM5ATR!=INVALID_HANDLE) IndicatorRelease(hM5ATR);
   if(hM1Fast!=INVALID_HANDLE) IndicatorRelease(hM1Fast);
   if(hM1Slow!=INVALID_HANDLE) IndicatorRelease(hM1Slow);
   if(hM1RSI!=INVALID_HANDLE) IndicatorRelease(hM1RSI);
   if(hM1ATR!=INVALID_HANDLE) IndicatorRelease(hM1ATR);
   if(hH1F!=INVALID_HANDLE) IndicatorRelease(hH1F);
   if(hH1S!=INVALID_HANDLE) IndicatorRelease(hH1S);
   if(hH4F!=INVALID_HANDLE) IndicatorRelease(hH4F);
   if(hH4S!=INVALID_HANDLE) IndicatorRelease(hH4S);
   if(hM30F!=INVALID_HANDLE) IndicatorRelease(hM30F);
   if(hM30S!=INVALID_HANDLE) IndicatorRelease(hM30S);
   WipePrefix();
   Comment("");
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   if(rates_total<80) return 0;

   g_gmtOff=BrokerGmtOff();

   if(!FeedsReady())
   {
      datetime phNow=BrokerToPh(TimeCurrent());
      MqlDateTime phTm; TimeToStruct(phNow,phTm);
      double lo=0,hi=0;
      VisibleBand(lo,hi);
      RedrawSessions(lo,hi);
      string h4s,h1s,m30s,biasS;
      double adxV=0,gapV=0,rsiV=0,slowEma=0,fastEma=0;
      ReadHtfPanel(time[rates_total-2],h4s,h1s,m30s,biasS,adxV,gapV,rsiV,slowEma,fastEma);
      Panel(close[rates_total-2],biasS,adxV,gapV,rsiV,h4s,h1s,m30s);
      return 0;
   }

   if(prev_calculated==0)
   {
      ArrayInitialize(BufBuy,EMPTY_VALUE);
      ArrayInitialize(BufSell,EMPTY_VALUE);
      ArrayInitialize(BufBias,EMPTY_VALUE);
      ArrayInitialize(BufFast,EMPTY_VALUE);
      WipeKind("AR_");
      WipeKind("SIG_");
      WipeKind("WAIT_");
      g_lastReason="";
      g_lastSide="";
      g_lastClock="";
      g_signalCount=0;
      g_waitCount=0;
      CsvEnsureHeader(true);
   }

   int biasStart=InpM5SlowEMA;
   if(prev_calculated>biasStart)
      biasStart=prev_calculated-1;
   for(int b=biasStart;b<rates_total;b++)
   {
      BufBias[b]=EMPTY_VALUE;
      BufFast[b]=EMPTY_VALUE;
      int sh=iBarShift(_Symbol,PERIOD_M5,time[b],false);
      double slow=0,fast=0;
      if(InpShowBiasLine && Read1(hM5Slow,0,sh,slow)) BufBias[b]=slow;
      if(InpShowFastEma && Read1(hM5Fast,0,sh,fast)) BufFast[b]=fast;
   }

   int start=InpM5SlowEMA+8;
   if(prev_calculated>start)
      start=prev_calculated-1;
   int lastClosed=rates_total-2;
   if(lastClosed>=start)
   {

   MqlRates m1all[];
   ArraySetAsSeries(m1all,false);
   int want=InpDaysBack*24*60+180;
   if(want<2000) want=2000;
   if(want>12000) want=12000;
   int nM1=CopyRates(_Symbol,PERIOD_M1,0,want,m1all);
   if(nM1<0) nM1=0;
   g_m1Bars=nM1;

   datetime lastOk=0;
   if(prev_calculated>0)
   {
      for(int j=MathMin(lastClosed,start)-1;j>=1;j--)
      {
         if((BufBuy[j]!=EMPTY_VALUE && BufBuy[j]>0) || (BufSell[j]!=EMPTY_VALUE && BufSell[j]>0))
         { lastOk=time[j]; break; }
      }
   }

   for(int i=start;i<=lastClosed;i++)
   {
      BufBuy[i]=EMPTY_VALUE;
      BufSell[i]=EMPTY_VALUE;

      int dir=0,scoreV=0,grade=0;
      string reason,h4s,h1s,m30s,biasS;
      double rsiV=0,adxV=0,gapV=0;
      if(!EvalBar(i,time,open,high,low,close,rates_total,m1all,nM1,
                  dir,reason,h4s,h1s,m30s,biasS,rsiV,adxV,gapV,scoreV,grade))
         continue;

      double y=DotY(high[i],low[i]);

      if(grade==2)
      {
         MarkWait(time[i],y,dir);
         continue;
      }

      if(InpMinBarsBetween>0 && lastOk>0)
      {
         int gapBars=iBarShift(_Symbol,_Period,lastOk,false)-iBarShift(_Symbol,_Period,time[i],false);
         if(gapBars>=0 && gapBars<InpMinBarsBetween) continue;
      }

      datetime ph=BrokerToPh(time[i]);
      MqlDateTime tm; TimeToStruct(ph,tm);
      string sess=SessionName(tm.hour);
      string clock=FormatPhClock(ph);
      string side=SideTxt(dir);

      if(dir>0)
      {
         BufBuy[i]=y;
         MarkSignal(time[i],y,1);
      }
      else
      {
         BufSell[i]=y;
         MarkSignal(time[i],y,-1);
      }

      if(InpLogCsv)
         CsvAppend(time[i],ph,clock,sess,side,close[i],h4s,h1s,m30s,biasS,adxV,gapV,rsiV,scoreV,reason);

      g_lastReason=reason;
      g_lastSide=side;
      g_lastClock=clock;
      lastOk=time[i];
   }
   }

   BufBuy[rates_total-1]=EMPTY_VALUE;
   BufSell[rates_total-1]=EMPTY_VALUE;

   g_signalCount=0;
   g_waitCount=0;
   for(int c=1;c<=lastClosed;c++)
   {
      if((BufBuy[c]!=EMPTY_VALUE && BufBuy[c]>0) || (BufSell[c]!=EMPTY_VALUE && BufSell[c]>0))
         g_signalCount++;
   }
   int totalObj=ObjectsTotal(0,0,-1);
   for(int o=totalObj-1;o>=0;o--)
   {
      string nm=ObjectName(0,o,0,-1);
      if(StringFind(nm,PREFIX+"WAIT_")==0) g_waitCount++;
   }

   double lo=0,hi=0;
   VisibleBand(lo,hi);
   datetime phNow=BrokerToPh(TimeCurrent());
   int ymd=PhYmd(phNow);
   MqlDateTime phTm; TimeToStruct(phNow,phTm);
   if(ymd!=g_lastPhYmd || phTm.hour!=g_lastPhHour || prev_calculated==0)
   {
      RedrawSessions(lo,hi);
      DrawPhHourLabels(time,rates_total);
      g_lastPhYmd=ymd;
      g_lastPhHour=phTm.hour;
   }
   RelayoutNames();
   RelayoutHours();
   DrawH4Sr();
   RefreshCards(time,high,low,BufBuy,BufSell,rates_total);

   int i=lastClosed;
   string h4s,h1s,m30s,biasS;
   double adxV=0,gapV=0,rsiV=0,slowEma=0,fastEma=0;
   ReadHtfPanel(time[i],h4s,h1s,m30s,biasS,adxV,gapV,rsiV,slowEma,fastEma);
   DrawBiasLabel(time[i],slowEma,biasS);
   Panel(close[i],biasS,adxV,gapV,rsiV,h4s,h1s,m30s);

   return rates_total;
}

void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam)
{
   if(id!=CHARTEVENT_CHART_CHANGE) return;
   double lo=0,hi=0;
   VisibleBand(lo,hi);
   RedrawSessions(lo,hi);
   RelayoutNames();
   RefreshHourLabels();
   ChartRedraw(0);
}
//+------------------------------------------------------------------+
