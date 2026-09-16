//+------------------------------------------------------------------+
//| JM_GOLD_Session_Signal_v1.mq5                                    |
//| Visual GOLD# validator: PH sessions + MTF signal arrows          |
//| NO ORDERS. CSV reason log for later EA conversion.               |
//+------------------------------------------------------------------+
#property copyright "JM Tech Solution"
#property version   "1.10"
#property description "GOLD# PH daily/session colors + hour labels on candles + BUY/SELL arrows. Walang auto trade."
#property indicator_chart_window
#property indicator_buffers 2
#property indicator_plots   2

#property indicator_label1  "BUY"
#property indicator_type1   DRAW_ARROW
#property indicator_color1  clrLime
#property indicator_width1  2

#property indicator_label2  "SELL"
#property indicator_type2   DRAW_ARROW
#property indicator_color2  clrTomato
#property indicator_width2  2

#define PREFIX "JMSS_"
#define CSV_NAME "JM_GOLD_Session_Signal_v1.csv"

input group "=== PH sessions (UTC+8) ==="
input int    InpPhUtcOffset         = 8;
input int    InpDaysBack            = 7;
input bool   InpDrawDaily           = true;
input bool   InpDrawSessions        = true;
input bool   InpDrawOpenLines       = true;
input bool   InpDrawPhHours         = true;   // "1PM" on the hour candle
input bool   InpDrawHourLines       = true;
input int    InpHourFontSize        = 8;
input double InpHourLabelPadUsd     = 0.35;
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
input int    InpZoneAlpha           = 62;

input group "=== Chart signal (M1/M5 entry) ==="
input int    InpEmaPeriod           = 50;
input int    InpRsiPeriod           = 14;
input double InpRsiBuyMin           = 45.0;
input double InpRsiBuyMax           = 70.0;
input double InpRsiSellMin          = 30.0;
input double InpRsiSellMax          = 55.0;
input int    InpBbPeriod            = 20;
input double InpBbDev               = 2.0;
input double InpArrowOffsetUsd      = 0.80;
input int    InpMinBarsBetween      = 4;
input int    InpMaxLabels           = 25;

input group "=== MTF filters (off = display only) ==="
input int    InpH4Fast              = 20;
input int    InpH4Slow              = 50;
input int    InpH1Fast              = 20;
input int    InpH1Slow              = 50;
input int    InpM15Fast             = 9;
input int    InpM15Slow             = 21;
input bool   InpRequireEma          = true;
input bool   InpRequireRsi          = true;
input bool   InpRequireBb           = true;
input bool   InpRequireCandle       = true;
input bool   InpRequireH1           = true;
input bool   InpRequireM15          = false;
input bool   InpRequireH4           = false;

input group "=== Display / log ==="
input bool   InpShowPanel           = true;
input bool   InpShowSignalCards     = true;
input bool   InpLogCsv              = true;
input bool   InpDrawH4Sr            = true;

double BufBuy[];
double BufSell[];
int hEma=INVALID_HANDLE,hRsi=INVALID_HANDLE,hBb=INVALID_HANDLE;
int hH1F=INVALID_HANDLE,hH1S=INVALID_HANDLE;
int hH4F=INVALID_HANDLE,hH4S=INVALID_HANDLE;
int hM15F=INVALID_HANDLE,hM15S=INVALID_HANDLE;
int g_lastPhYmd=-1;
int g_lastPhHour=-1;
int g_gmtOff=0;
string g_lastReason="";

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

int EmaSide(const double close,const double ema)
{
   if(close>ema) return 1;
   if(close<ema) return -1;
   return 0;
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
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,(long)ColorToARGB(clr,(uchar)MathMax(10,MathMin(alpha,120))));
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

void StyleHourOnCandle(const string name,const datetime t,const double price,
                       const string text,const color clr)
{
   if(ObjectFind(0,name)<0)
      ObjectCreate(0,name,OBJ_TEXT,0,t,price);
   ObjectMove(0,name,0,t,price);
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,InpHourFontSize);
   ObjectSetString(0,name,OBJPROP_FONT,"Arial Bold");
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_LOWER);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,name,OBJPROP_BACK,false);
}

void StyleTag(const string name,const datetime t,const double price,
              const string text,const color clr)
{
   if(ObjectFind(0,name)<0)
      ObjectCreate(0,name,OBJ_TEXT,0,t,price);
   ObjectMove(0,name,0,t,price);
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,9);
   ObjectSetString(0,name,OBJPROP_FONT,"Arial Bold");
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
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
   StyleTag(PREFIX+"T_"+key,t1,hi,label,clr);
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
      if(dt.day_of_week==0 || dt.day_of_week==6) continue;
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
         StyleTag(PREFIX+"T_DAY_"+ymd,t1,hi+InpArrowOffsetUsd*2,
                  StringFormat("DAILY PH 00:00-23:59  %04d-%02d-%02d",dt.year,dt.mon,dt.day),clrWhite);
      }

      if(!InpDrawSessions) continue;

      DrawSessionSpan(ymd+"_ASIA",day0,InpAsiaStart,InpAsiaEnd,lo,hi,InpClrAsia,
                      StringFormat("ASIAN/TOKYO  %02d:00-%02d:00 PH",InpAsiaStart,(InpAsiaEnd==0?24:InpAsiaEnd)),true);
      DrawSessionSpan(ymd+"_LON",day0,InpLondonStart,InpLondonEnd,lo,hi,InpClrLondon,
                      StringFormat("LONDON  %02d:00-%02d:00 PH",InpLondonStart,(InpLondonEnd==0?24:InpLondonEnd)),true);
      DrawSessionSpan(ymd+"_NY",day0,InpNyStart,InpNyEnd,lo,hi,InpClrNy,
                      StringFormat("NEW YORK  %02d:00-%02d:00 PH",InpNyStart,(InpNyEnd==0?24:InpNyEnd)),true);
      DrawSessionSpan(ymd+"_OVLP",day0,InpOverlapStart,InpOverlapEnd,
                      lo+(hi-lo)*0.04,hi-(hi-lo)*0.04,InpClrOverlap,
                      "LONDON-NY OVERLAP PH",true);
   }
}

void DrawPhHourLabels(const datetime &time[],const double &high[],const double &low[],const int rates_total)
{
   WipeKind("HR_");
   WipeKind("HL_");
   if(!InpDrawPhHours || rates_total<10) return;

   datetime phNow=BrokerToPh(TimeCurrent());
   datetime startPh=PhMidnight(phNow)-(datetime)InpDaysBack*86400;
   datetime startBr=PhToBroker(startPh);

   int i0=0;
   for(int i=0;i<rates_total;i++)
   {
      if(time[i]>=startBr) { i0=i; break; }
   }

   int lastH=-1;
   int lastYmd=-1;
   for(int i=i0;i<rates_total;i++)
   {
      datetime ph=BrokerToPh(time[i]);
      MqlDateTime t; TimeToStruct(ph,t);
      int ymd=t.year*10000+t.mon*100+t.day;
      if(t.hour==lastH && ymd==lastYmd) continue;
      lastH=t.hour;
      lastYmd=ymd;

      string key=StringFormat("%d_%02d",ymd,t.hour);
      color clr=SessionColor(t.hour);
      double px=high[i]+InpHourLabelPadUsd;
      StyleHourOnCandle(PREFIX+"HR_"+key,time[i],px,FormatPhHour(t.hour),clr);
      if(InpDrawHourLines)
      {
         StyleVLine(PREFIX+"HL_"+key,time[i],clr,STYLE_DOT);
         ObjectSetInteger(0,PREFIX+"HL_"+key,OBJPROP_WIDTH,1);
      }
   }
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
                "h4","h1","m15","ema","rsi","bb","candle","reason");
   }
   FileClose(fh);
}

void CsvAppend(const datetime br,const datetime ph,const string clock,const string sess,
               const string side,const double entry,const string h4,const string h1,const string m15,
               const string ema,const double rsi,const string bb,const string candle,const string reason)
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
             h4,h1,m15,ema,
             DoubleToString(rsi,1),
             bb,candle,reason);
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
      string arrow=buySide?"BUY ▲":"SELL ▼";
      double entry=buySide?buy[i]+InpArrowOffsetUsd:sell[i]-InpArrowOffsetUsd;

      int shH1=ClosedHtfShift(PERIOD_H1,time[i]);
      int shM15=ClosedHtfShift(PERIOD_M15,time[i]);
      double h1f=0,h1s=0,m15f=0,m15s=0;
      string h1="FLAT", m15="FLAT";
      if(Read1(hH1F,0,shH1,h1f) && Read1(hH1S,0,shH1,h1s)) h1=SideTxt(HtfSide(h1f,h1s));
      if(Read1(hM15F,0,shM15,m15f) && Read1(hM15S,0,shM15,m15s)) m15=SideTxt(HtfSide(m15f,m15s));

      string card=StringFormat("%s\nPH TIME: %s\nSESSION: %s\nH1 TREND: %s\nM15 MOMENTUM: %s\nENTRY: %s",
                               arrow,FormatPhClock(ph),sess,h1,m15,DoubleToString(entry,_Digits));
      double px=buySide?low[i]-InpArrowOffsetUsd*3.0:high[i]+InpArrowOffsetUsd*1.2;
      PutCard(found,time[i],px,card,buySide?clrLime:clrTomato);
      found++;
   }
}

void Panel(const double close,const string emaS,const double rsi,
           const string h4,const string h1,const string m15)
{
   if(!InpShowPanel) return;
   datetime ph=BrokerToPh(TimeCurrent());
   MqlDateTime tm; TimeToStruct(ph,tm);
   string sess=SessionName(tm.hour);
   MqlDateTime br; TimeToStruct(TimeCurrent(),br);

   Comment("JM GOLD SESSION SIGNAL v1  |  VISUAL ONLY — walang order\n",
           "PH TIME  ",FormatPhClock(ph),
           StringFormat("   %04d-%02d-%02d",tm.year,tm.mon,tm.day),
           "   SESSION: ",sess,"\n",
           "Daily PH 00:00-23:59 | Asia gold | London blue | NY green | Overlap purple\n",
           "Hour labels on candles: 12AM 1AM ... 1PM 2PM ... 11PM\n",
           "H4 TREND: ",h4,"   H1 TREND: ",h1,"   M15 MOMENTUM: ",m15,"\n",
           "CHART ",EnumToString(_Period),
           "  EMA",IntegerToString(InpEmaPeriod)," ",emaS,
           "  RSI ",DoubleToString(rsi,1),
           "  close ",DoubleToString(close,_Digits),"\n",
           "Filters  EMA=",(InpRequireEma?"ON":"off"),
           " RSI=",(InpRequireRsi?"ON":"off"),
           " BB=",(InpRequireBb?"ON":"off"),
           " CANDLE=",(InpRequireCandle?"ON":"off"),
           " H1=",(InpRequireH1?"ON":"off"),
           " M15=",(InpRequireM15?"ON":"off"),
           " H4=",(InpRequireH4?"ON":"off"),"\n",
           "CSV  MQL5\\Files\\",CSV_NAME,"\n",
           (g_lastReason==""?"Last signal: none yet":"Last: "+g_lastReason),"\n",
           "Broker H",IntegerToString(br.hour),"  (offset vs GMT ",IntegerToString(g_gmtOff/3600),"h)");
}

int OnInit()
{
   SetIndexBuffer(0,BufBuy,INDICATOR_DATA);
   SetIndexBuffer(1,BufSell,INDICATOR_DATA);
   PlotIndexSetInteger(0,PLOT_ARROW,233);
   PlotIndexSetInteger(1,PLOT_ARROW,234);
   PlotIndexSetDouble(0,PLOT_EMPTY_VALUE,EMPTY_VALUE);
   PlotIndexSetDouble(1,PLOT_EMPTY_VALUE,EMPTY_VALUE);
   ArraySetAsSeries(BufBuy,false);
   ArraySetAsSeries(BufSell,false);
   IndicatorSetString(INDICATOR_SHORTNAME,"JM GOLD Session Signal v1");

   hEma=iMA(_Symbol,_Period,InpEmaPeriod,0,MODE_EMA,PRICE_CLOSE);
   hRsi=iRSI(_Symbol,_Period,InpRsiPeriod,PRICE_CLOSE);
   hBb =iBands(_Symbol,_Period,InpBbPeriod,0,InpBbDev,PRICE_CLOSE);
   hH1F=iMA(_Symbol,PERIOD_H1,InpH1Fast,0,MODE_EMA,PRICE_CLOSE);
   hH1S=iMA(_Symbol,PERIOD_H1,InpH1Slow,0,MODE_EMA,PRICE_CLOSE);
   hH4F=iMA(_Symbol,PERIOD_H4,InpH4Fast,0,MODE_EMA,PRICE_CLOSE);
   hH4S=iMA(_Symbol,PERIOD_H4,InpH4Slow,0,MODE_EMA,PRICE_CLOSE);
   hM15F=iMA(_Symbol,PERIOD_M15,InpM15Fast,0,MODE_EMA,PRICE_CLOSE);
   hM15S=iMA(_Symbol,PERIOD_M15,InpM15Slow,0,MODE_EMA,PRICE_CLOSE);

   if(hEma==INVALID_HANDLE || hRsi==INVALID_HANDLE || hBb==INVALID_HANDLE ||
      hH1F==INVALID_HANDLE || hH1S==INVALID_HANDLE ||
      hH4F==INVALID_HANDLE || hH4S==INVALID_HANDLE ||
      hM15F==INVALID_HANDLE || hM15S==INVALID_HANDLE)
      return INIT_FAILED;

   g_gmtOff=BrokerGmtOff();
   CsvEnsureHeader(true);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hEma!=INVALID_HANDLE) IndicatorRelease(hEma);
   if(hRsi!=INVALID_HANDLE) IndicatorRelease(hRsi);
   if(hBb!=INVALID_HANDLE) IndicatorRelease(hBb);
   if(hH1F!=INVALID_HANDLE) IndicatorRelease(hH1F);
   if(hH1S!=INVALID_HANDLE) IndicatorRelease(hH1S);
   if(hH4F!=INVALID_HANDLE) IndicatorRelease(hH4F);
   if(hH4S!=INVALID_HANDLE) IndicatorRelease(hH4S);
   if(hM15F!=INVALID_HANDLE) IndicatorRelease(hM15F);
   if(hM15S!=INVALID_HANDLE) IndicatorRelease(hM15S);
   WipePrefix();
   Comment("");
}

bool EvalBar(const int i,const datetime &time[],
             const double &open[],const double &high[],
             const double &low[],const double &close[],
             int &dirOut,string &reasonOut,string &bbTag,string &candleTag,
             string &h4s,string &h1s,string &m15s,string &emaS,double &rsiV)
{
   dirOut=0;
   reasonOut="";
   bbTag="NONE";
   candleTag="DOJI";
   h4s="FLAT"; h1s="FLAT"; m15s="FLAT"; emaS="FLAT"; rsiV=0;

   int chartShift=iBarShift(_Symbol,_Period,time[i],false);
   if(chartShift<0) return false;

   double ema=0,rsi=0,rsiPrev=0,bbU=0,bbL=0;
   if(!Read1(hEma,0,chartShift,ema)) return false;
   if(!Read1(hRsi,0,chartShift,rsi) || !Read1(hRsi,0,chartShift+1,rsiPrev)) return false;
   if(!Read1(hBb,1,chartShift,bbU) || !Read1(hBb,2,chartShift,bbL)) return false;
   rsiV=rsi;
   emaS=SideTxt(EmaSide(close[i],ema));

   int shH4=ClosedHtfShift(PERIOD_H4,time[i]);
   int shH1=ClosedHtfShift(PERIOD_H1,time[i]);
   int shM15=ClosedHtfShift(PERIOD_M15,time[i]);
   double h4f=0,h4w=0,h1f=0,h1w=0,m15f=0,m15w=0;
   if(Read1(hH4F,0,shH4,h4f) && Read1(hH4S,0,shH4,h4w)) h4s=SideTxt(HtfSide(h4f,h4w));
   if(Read1(hH1F,0,shH1,h1f) && Read1(hH1S,0,shH1,h1w)) h1s=SideTxt(HtfSide(h1f,h1w));
   if(Read1(hM15F,0,shM15,m15f) && Read1(hM15S,0,shM15,m15w)) m15s=SideTxt(HtfSide(m15f,m15w));

   bool bull=close[i]>open[i];
   bool bear=close[i]<open[i];
   candleTag=bull?"BULL":(bear?"BEAR":"DOJI");

   bool bbBuy=(low[i]<=bbL && close[i]>bbL && bull);
   bool bbSell=(high[i]>=bbU && close[i]<bbU && bear);
   bbTag=bbBuy?"LOWER_BOUNCE":(bbSell?"UPPER_BOUNCE":"NONE");

   bool rsiBuy=(rsi>=InpRsiBuyMin && rsi<=InpRsiBuyMax && rsi>rsiPrev);
   bool rsiSell=(rsi>=InpRsiSellMin && rsi<=InpRsiSellMax && rsi<rsiPrev);

   for(int attempt=1; attempt>=-1; attempt-=2)
   {
      int side=attempt;
      string sTxt=SideTxt(side);
      if(InpRequireEma && emaS!=sTxt) continue;
      if(InpRequireCandle && ((side>0 && !bull) || (side<0 && !bear))) continue;
      if(InpRequireRsi && ((side>0 && !rsiBuy) || (side<0 && !rsiSell))) continue;
      if(InpRequireBb && ((side>0 && !bbBuy) || (side<0 && !bbSell))) continue;
      if(InpRequireH1 && h1s!=sTxt) continue;
      if(InpRequireM15 && m15s!=sTxt) continue;
      if(InpRequireH4 && h4s!=sTxt) continue;

      datetime ph=BrokerToPh(time[i]);
      MqlDateTime tm; TimeToStruct(ph,tm);
      string sess=SessionName(tm.hour);
      string clock=FormatPhClock(ph);
      reasonOut=StringFormat("SIDE=%s|PH=%s|SESSION=%s|ENTRY=%.2f|H4=%s|H1=%s|M15=%s|EMA=%s|RSI=%.1f|BB=%s|CANDLE=%s",
                             sTxt,clock,sess,close[i],h4s,h1s,m15s,emaS,rsi,bbTag,candleTag);
      dirOut=side;
      return true;
   }
   return false;
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

   if(prev_calculated==0)
   {
      ArrayInitialize(BufBuy,EMPTY_VALUE);
      ArrayInitialize(BufSell,EMPTY_VALUE);
      CsvEnsureHeader(true);
   }

   int start=InpBbPeriod+InpEmaPeriod+5;
   if(prev_calculated>start)
      start=prev_calculated-1;
   int lastClosed=rates_total-2;
   if(lastClosed<start) return rates_total;

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

      int dir=0;
      string reason,bbTag,candleTag,h4s,h1s,m15s,emaS;
      double rsiV=0;
      if(!EvalBar(i,time,open,high,low,close,dir,reason,bbTag,candleTag,h4s,h1s,m15s,emaS,rsiV))
         continue;

      if(InpMinBarsBetween>0 && lastOk>0)
      {
         int gap=iBarShift(_Symbol,_Period,lastOk,false)-iBarShift(_Symbol,_Period,time[i],false);
         if(gap>=0 && gap<InpMinBarsBetween) continue;
      }

      datetime ph=BrokerToPh(time[i]);
      MqlDateTime tm; TimeToStruct(ph,tm);
      string sess=SessionName(tm.hour);
      string clock=FormatPhClock(ph);
      string side=SideTxt(dir);

      if(dir>0) BufBuy[i]=low[i]-InpArrowOffsetUsd;
      else      BufSell[i]=high[i]+InpArrowOffsetUsd;

      if(InpLogCsv)
         CsvAppend(time[i],ph,clock,sess,side,close[i],h4s,h1s,m15s,emaS,rsiV,bbTag,candleTag,reason);

      g_lastReason=reason;
      lastOk=time[i];
   }

   BufBuy[rates_total-1]=EMPTY_VALUE;
   BufSell[rates_total-1]=EMPTY_VALUE;

   int n=MathMin(rates_total,2000);
   double lo=low[ArrayMinimum(low,rates_total-n,n)];
   double hi=high[ArrayMaximum(high,rates_total-n,n)];
   double pad=MathMax(8.0,(hi-lo)*0.04);
   datetime phNow=BrokerToPh(TimeCurrent());
   int ymd=PhYmd(phNow);
   MqlDateTime phTm; TimeToStruct(phNow,phTm);
   if(ymd!=g_lastPhYmd || phTm.hour!=g_lastPhHour || prev_calculated==0)
   {
      RedrawSessions(lo-pad,hi+pad);
      DrawPhHourLabels(time,high,low,rates_total);
      g_lastPhYmd=ymd;
      g_lastPhHour=phTm.hour;
   }
   DrawH4Sr();
   RefreshCards(time,high,low,BufBuy,BufSell,rates_total);

   string h4s="FLAT",h1s="FLAT",m15s="FLAT",emaS="FLAT";
   double rsiV=0,ema=0,h4f=0,h4w=0,h1f=0,h1w=0,m15f=0,m15w=0;
   int i=lastClosed;
   int cs=iBarShift(_Symbol,_Period,time[i],false);
   Read1(hEma,0,cs,ema); emaS=SideTxt(EmaSide(close[i],ema));
   Read1(hRsi,0,cs,rsiV);
   int shH4=ClosedHtfShift(PERIOD_H4,time[i]);
   int shH1=ClosedHtfShift(PERIOD_H1,time[i]);
   int shM15=ClosedHtfShift(PERIOD_M15,time[i]);
   if(Read1(hH4F,0,shH4,h4f) && Read1(hH4S,0,shH4,h4w)) h4s=SideTxt(HtfSide(h4f,h4w));
   if(Read1(hH1F,0,shH1,h1f) && Read1(hH1S,0,shH1,h1w)) h1s=SideTxt(HtfSide(h1f,h1w));
   if(Read1(hM15F,0,shM15,m15f) && Read1(hM15S,0,shM15,m15w)) m15s=SideTxt(HtfSide(m15f,m15w));
   Panel(close[i],emaS,rsiV,h4s,h1s,m15s);

   return rates_total;
}
//+------------------------------------------------------------------+
