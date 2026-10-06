//+------------------------------------------------------------------+
//|                                JM Thunder Gold Scalper v2.0.3.mq5 |
//|                         Structure. Momentum. Precision. (XAUUSD) |
//| v2.0.2 + manual stop/limit trail: start $0.50 @ 0.01, dist $0.70 |
//+------------------------------------------------------------------+
#property copyright "JM Thunder Gold Scalper v2.0.3"
#property version   "2.03"
#property description "XAUUSD M15 structure-breakout scalper + manual pending trail manager."
#property description "Stop orders at swing highs/lows. Your SL/TP on manual stops/limits."
#property description "After fill, EA trails from $0.50 (0.01 lot) using Thunder pullback distance."
#property description "NO grid. NO martingale. NO averaging. News: allow WebRequest https://nfs.faireconomy.media"

#include <Trade/Trade.mqh>

enum ENUM_BROKER_TYPE
  {
   BROKER_DEFAULT = 0, // Default
   BROKER_EXNESS  = 1  // Exness
  };

input group "=== CORE ==="
input long             InpMagic            = 30250003;
input string           InpComment          = "JM ThunderGold v2.0.3";

input group "=== BROKER TYPE ==="
input ENUM_BROKER_TYPE InpBroker           = BROKER_DEFAULT;

input group "=== MONEY MANAGEMENT ==="
input bool             InpUseFixedLot      = false;
input double           InpFixedLot         = 0.01;
input double           InpRiskPercent      = 5.0;

input group "=== SL / TP / TRAILING (0 points = USD / EA default) ==="
input int              InpSLPoints         = 0;
input int              InpTPPoints         = 0;
input int              InpTrailStart       = 0;                 // 0 = use USD start ($0.50)
input int              InpTrailStep        = 0;                 // 0 = use USD step ($0.10)
input int              InpTrailDistance    = 0;                 // 0 = use USD distance ($0.70 original)
input bool             InpUseTrailing      = true;
input double           InpTrailStartUsd    = 0.50;              // Trail starts after +$0.50 gold @ 0.01
input double           InpTrailDistanceUsd = 0.70;              // Original Thunder pullback (70 pts)
input double           InpTrailStepUsd     = 0.10;              // Original Thunder step (10 pts)
input double           InpBreakevenUsd     = 1.0;
input int              InpBreakevenLockPts = 10;
input double           InpRefLot           = 0.01;
input double           InpSLUsd            = 2.0;
input bool             InpAtrStops         = false;
input double           InpAtrSLMult        = 1.0;
input double           InpAtrSLMinUsd      = 1.0;
input double           InpAtrSLMaxUsd      = 8.0;
input double           InpTrailStartR      = 1.5;
input double           InpTrailDistR       = 0.4;
input double           InpTrailStepR       = 0.05;
input bool             InpDynamicTP        = false;
input double           InpTP1Usd           = 25.0;
input double           InpTP2Usd           = 30.0;
input double           InpTP3Usd           = 40.0;
input double           InpTP4Usd           = 50.0;
input double           InpTP5Usd           = 60.0;
input double           InpTP6Usd           = 65.0;
input double           InpADXLevel2        = 20.0;
input double           InpADXLevel3        = 25.0;
input double           InpADXLevel4        = 30.0;
input double           InpADXLevel5        = 35.0;
input double           InpADXLevel6        = 40.0;
input int              InpADXPeriod        = 14;

input group "=== MANUAL ENTRY TRAIL ==="
input bool             InpManageManual     = true;              // Trail YOUR buy/sell stop + limit fills
input bool             InpPauseAutoWhenManual = true;           // Pause EA stops while you have a manual order/position
input bool             InpManualKeepStops  = true;              // Keep your SL/TP; EA only trails SL in profit

input group "=== NEWS GUARD ==="
input bool             InpNewsGuard        = false;
input int              InpNewsBefore       = 30;
input int              InpNewsAfter        = 30;
input string           InpNewsCurrencies   = "USD";

input group "=== CALENDAR SHIELD ==="
input bool             InpCancelOnHolidays = true;

input group "=== PROTECTION ==="
input bool             InpFridayClose      = true;
input int              InpFridayCloseHour  = 17;
input int              InpTesterGMTOffset  = 3;
input int              InpMaxSpread        = 50;
input int              InpMaxSlippage      = 30;
input int              InpMaxTradesPerDay  = 5;
input int              InpCooldownBars     = 4;

input group "=== STRATEGY ==="
input ENUM_TIMEFRAMES  InpSignalTF         = PERIOD_M15;
input int              InpEmaFast          = 20;
input int              InpEmaSlow          = 200;
input int              InpRsiPeriod        = 14;
input int              InpSwingStrength    = 5;
input int              InpSwingLookback    = 192;
input int              InpEntryBuffer      = 50;
input int              InpMaxEntryDistance = 5000;
input int              InpPendingExpiryBars= 192;
input bool             InpNeutralBothSides = false;

input group "=== FILTERS ==="
input bool             InpTrendFilter      = true;
input bool             InpMomentumFilter   = true;
input bool             InpCandleFilter     = true;
input double           InpMinBodyRatio     = 0.40;
input bool             InpVolumeFilter     = true;
input int              InpVolumePeriod     = 20;
input double           InpVolumeMult       = 1.0;
input bool             InpExtensionFilter  = false;
input int              InpAtrPeriod        = 14;
input double           InpMaxEmaDistAtr    = 2.0;
input double           InpMinAtrUsd        = 2.5;
input bool             InpSessionFilter    = true;
input bool             InpCancelOutside    = false;
input int              InpSessionStart     = 8;
input int              InpSessionEnd       = 21;

input group "=== DASHBOARD ==="
input bool             InpShowHUD          = true;
input int              InpPanelX           = 15;
input int              InpPanelY           = 15;
input double           InpPanelScale       = 0.0;
input bool             InpTesterRedrawBar  = true;
input int              InpRefreshSec       = 2;

input group "=== TRADE MARKERS ==="
input bool             InpShowPnLLabels    = true;

input group "=== DIAGNOSTICS ==="
input bool             InpVerbose          = false;
input bool             InpAnalyzer         = true;

#define DEF_TP_POINTS        3000
#define DEF_TRAIL_START_PTS  50
#define DEF_TRAIL_STEP_PTS   10
#define DEF_TRAIL_DISTANCE_PTS 70

#define NEWS_URL             "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
#define NEWS_REFRESH_SEC     14400
#define NEWS_RETRY_SEC       300

#define CLR_BG       C'11,13,18'
#define CLR_BOX      C'17,20,27'
#define CLR_GOLD     C'212,175,55'
#define CLR_GOLD_DIM C'120,98,35'
#define CLR_TEXT     C'215,215,220'
#define CLR_MUTED    C'125,128,138'
#define CLR_GREEN    C'46,204,113'
#define CLR_RED      C'231,76,60'

const string PFX = "JMTG_";
string BOLT = ShortToString(0x03DF);

struct NewsEvent
  {
   datetime gmt;
   string   ccy;
   string   title;
  };

CTrade   trade;
int      hEmaFast = INVALID_HANDLE;
int      hEmaSlow = INVALID_HANDLE;
int      hRsi     = INVALID_HANDLE;
int      hAtr     = INVALID_HANDLE;
int      hAdx     = INVALID_HANDLE;

datetime g_lastBar        = 0;
datetime g_lastHudBar     = 0;
int      g_trend          = 0;
bool     g_isTester       = false;
bool     g_isVisual       = false;
double   g_scale          = 1.0;

int      g_pf;
int      g_slPts, g_tpPts, g_trailStart, g_trailStep, g_trailDist;
int      g_bufferPts, g_maxEntryPts, g_maxSpreadPts;

double   g_profitDay = 0, g_profitMonth = 0, g_profitTotal = 0;
double   g_grossProfit = 0, g_grossLoss = 0;
int      g_wins = 0, g_losses = 0, g_tradesToday = 0;
datetime g_lastCloseTime = 0;
datetime g_statsDay = 0;
datetime g_marketClosedUntil = 0;
double   g_lastSlippage = -1;
double   g_nextLot = 0;
ulong    g_reanchorPos = 0;
int      g_reanchorTpPts = 0;
ulong    g_posId = 0;
int      g_posSlPts = 0;

NewsEvent g_news[];
datetime g_newsFetched  = 0;
datetime g_newsAttempt  = 0;
bool     g_newsWebOK    = true;
bool     g_newsActive   = false;
string   g_newsInfo     = "";
bool     g_holiday      = false;
datetime g_holidayDay   = 0;
string   g_status       = "RUNNING";

void Log(string msg)
  {
   if(InpVerbose)
      Print("[JM ThunderGold] ", msg);
  }

int UsdToPoints(double usd);

int TrailPtsFromUsd(const double usd, const int fallbackPts)
  {
   int pts = UsdToPoints(usd);
   if(pts > 0)
      return pts;
   return fallbackPts * g_pf;
  }

int OnInit()
  {
   g_isTester = (bool)MQLInfoInteger(MQL_TESTER);
   g_isVisual = (bool)MQLInfoInteger(MQL_VISUAL_MODE);

   g_pf           = (InpBroker == BROKER_EXNESS) ? 10 : 1;
   g_slPts        = InpSLPoints > 0 ? InpSLPoints * g_pf : UsdToPoints(InpSLUsd);
   g_tpPts        = (InpTPPoints      > 0 ? InpTPPoints      : DEF_TP_POINTS) * g_pf;
   g_trailStart   = InpTrailStart    > 0 ? InpTrailStart    * g_pf : TrailPtsFromUsd(InpTrailStartUsd, DEF_TRAIL_START_PTS);
   g_trailStep    = InpTrailStep     > 0 ? InpTrailStep     * g_pf : TrailPtsFromUsd(InpTrailStepUsd, DEF_TRAIL_STEP_PTS);
   g_trailDist    = InpTrailDistance > 0 ? InpTrailDistance * g_pf : TrailPtsFromUsd(InpTrailDistanceUsd, DEF_TRAIL_DISTANCE_PTS);
   g_bufferPts    = InpEntryBuffer      * g_pf;
   g_maxEntryPts  = InpMaxEntryDistance * g_pf;
   g_maxSpreadPts = InpMaxSpread        * g_pf;

   if(g_slPts <= 0)
     {
      Print("Cannot convert SL USD to points (tick value unavailable). Set Stop Loss in points.");
      return INIT_FAILED;
     }

   if(InpAtrStops && (InpAtrSLMult <= 0 || InpTrailStartR - InpTrailDistR <= 0))
     {
      Print("ATR mode needs SL multiplier > 0 and trailing start > trailing distance.");
      return INIT_PARAMETERS_INCORRECT;
     }

   if(InpRiskPercent <= 0 && !InpUseFixedLot)
     {
      Print("Risk Per Trade must be > 0 when fixed lot is off.");
      return INIT_PARAMETERS_INCORRECT;
     }

   hEmaFast = iMA(_Symbol, InpSignalTF, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   hEmaSlow = iMA(_Symbol, InpSignalTF, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   hRsi     = iRSI(_Symbol, InpSignalTF, InpRsiPeriod, PRICE_CLOSE);
   hAtr     = iATR(_Symbol, InpSignalTF, InpAtrPeriod);
   hAdx     = iADX(_Symbol, InpSignalTF, InpADXPeriod);
   if(hEmaFast == INVALID_HANDLE || hEmaSlow == INVALID_HANDLE || hRsi == INVALID_HANDLE
      || hAtr == INVALID_HANDLE || hAdx == INVALID_HANDLE)
     {
      Print("Failed to create indicator handles: ", GetLastError());
      return INIT_FAILED;
     }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpMaxSlippage * g_pf);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.LogLevel(InpVerbose ? LOG_LEVEL_ALL : LOG_LEVEL_ERRORS);

   if(g_isVisual || !g_isTester)
     {
      ChartIndicatorAdd(0, 0, hEmaFast);
      ChartIndicatorAdd(0, 0, hEmaSlow);
     }

   RecalcStats();
   g_trend = GetTrend();

   if(InpNewsGuard && !g_isTester)
      FetchNews();

   if(!g_isTester && InpRefreshSec > 0)
      EventSetTimer(InpRefreshSec);

   if(HudEnabled())
      DrawHUD();

   PrintFormat("JM Thunder Gold Scalper v2.0.3 | ManualTrail=%s | TrailStart=$%.2f (%d pts) Dist=$%.2f (%d pts) Step=$%.2f (%d pts)",
               InpManageManual ? "ON" : "OFF",
               InpTrailStartUsd, g_trailStart,
               InpTrailDistanceUsd, g_trailDist,
               InpTrailStepUsd, g_trailStep);
   PrintFormat("Place YOUR buy/sell STOP or LIMIT with your SL/TP. After fill, EA trails from $%.2f using original Thunder distance.",
               InpTrailStartUsd);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(hEmaFast != INVALID_HANDLE) IndicatorRelease(hEmaFast);
   if(hEmaSlow != INVALID_HANDLE) IndicatorRelease(hEmaSlow);
   if(hRsi     != INVALID_HANDLE) IndicatorRelease(hRsi);
   if(hAtr     != INVALID_HANDLE) IndicatorRelease(hAtr);
   if(hAdx     != INVALID_HANDLE) IndicatorRelease(hAdx);
   if(!g_isTester)
      ObjectsDeleteAll(0, PFX);
  }

bool HudEnabled()
  {
   return InpShowHUD && (!g_isTester || g_isVisual);
  }

void OnTimer()
  {
   if(HudEnabled())
      DrawHUD();
   DrawNewsWarning();
  }

void OnTick()
  {
   AnalyzerTrack();
   bool newBar = IsNewBar();

   datetime now = TimeCurrent();
   if(now - (now % 86400) != g_statsDay)
      RecalcStats();

   UpdateGuards();
   bool blocked = ProtectionBlock();

   if(!MarketBlocked())
      ManagePositions();

   if(!blocked && !MarketBlocked())
     {
      ManagePendingExpiry();
      if(newBar)
         EvaluateSignal();
     }

   if(HudEnabled() && g_isTester)
     {
      datetime bt = iTime(_Symbol, PERIOD_CURRENT, 0);
      if(!InpTesterRedrawBar || bt != g_lastHudBar)
        {
         g_lastHudBar = bt;
         DrawHUD();
        }
     }
  }

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;
   if(HistoryDealGetString(trans.deal, DEAL_SYMBOL) != _Symbol)
      return;
   long mag = HistoryDealGetInteger(trans.deal, DEAL_MAGIC);
   bool ea  = (mag == InpMagic);
   bool man = (InpManageManual && mag == 0);
   if(!ea && !man)
      return;

   ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   double dealPrice      = HistoryDealGetDouble(trans.deal, DEAL_PRICE);

   if(entry == DEAL_ENTRY_IN)
     {
      if(ea)
        {
         ulong orderTicket = (ulong)HistoryDealGetInteger(trans.deal, DEAL_ORDER);
         if(HistoryOrderSelect(orderTicket))
           {
            double reqPrice = HistoryOrderGetDouble(orderTicket, ORDER_PRICE_OPEN);
            double orderSL  = HistoryOrderGetDouble(orderTicket, ORDER_SL);
            g_posId    = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
            g_posSlPts = (reqPrice > 0 && orderSL > 0) ? (int)MathRound(MathAbs(reqPrice - orderSL) / _Point) : 0;
            if(reqPrice > 0)
              {
               g_lastSlippage = MathAbs(dealPrice - reqPrice) / _Point;
               if(g_lastSlippage >= 1)
                 {
                  g_reanchorPos = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
                  double orderTP = HistoryOrderGetDouble(orderTicket, ORDER_TP);
                  g_reanchorTpPts = orderTP > 0 ? (int)MathRound(MathAbs(orderTP - reqPrice) / _Point) : 0;
                 }
              }
           }
         DeleteAllPendings();
         AnalyzerOnEntry(trans.deal, dealPrice);
        }
      else
        {
         PrintFormat("Manual fill detected | trail starts at $%.2f | distance $%.2f | your SL/TP kept",
                     InpTrailStartUsd, InpTrailDistanceUsd);
         AnalyzerOnEntry(trans.deal, dealPrice);
        }
     }
   else
     {
      double net = HistoryDealGetDouble(trans.deal, DEAL_PROFIT)
                   + HistoryDealGetDouble(trans.deal, DEAL_SWAP)
                   + HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
      AnalyzerOnExit(trans.deal, dealPrice, net);
      if(InpShowPnLLabels && (g_isVisual || !g_isTester))
         DrawClosedLabel(trans.deal, (datetime)HistoryDealGetInteger(trans.deal, DEAL_TIME), dealPrice, net);
     }

   RecalcStats();
  }

datetime GMTNow()
  {
   if(g_isTester)
      return TimeCurrent() - InpTesterGMTOffset * 3600;
   return TimeGMT();
  }

bool IsNewBar()
  {
   datetime t = iTime(_Symbol, InpSignalTF, 0);
   if(t == 0 || t == g_lastBar)
      return false;
   g_lastBar = t;
   return true;
  }

bool InSession()
  {
   if(!InpSessionFilter)
      return true;
   MqlDateTime g;
   TimeToStruct(GMTNow(), g);
   if(InpSessionStart <= InpSessionEnd)
      return g.hour >= InpSessionStart && g.hour < InpSessionEnd;
   return g.hour >= InpSessionStart || g.hour < InpSessionEnd;
  }

bool FridayCloseActive()
  {
   if(!InpFridayClose)
      return false;
   MqlDateTime g;
   TimeToStruct(GMTNow(), g);
   if(g.day_of_week == 6 || g.day_of_week == 0)
      return true;
   return g.day_of_week == 5 && g.hour >= InpFridayCloseHour;
  }

bool CurrencyWatched(string ccy)
  {
   string list = InpNewsCurrencies;
   StringReplace(list, " ", "");
   if(list == "")
      return true;
   StringToUpper(list);
   StringToUpper(ccy);
   string parts[];
   int n = StringSplit(list, ',', parts);
   for(int i = 0; i < n; i++)
      if(parts[i] == ccy)
         return true;
   return false;
  }

bool FixedHoliday(datetime t)
  {
   MqlDateTime d;
   TimeToStruct(t, d);
   if(d.mon == 12 && (d.day == 24 || d.day == 25 || d.day == 26 || d.day == 31))
      return true;
   if(d.mon == 1 && d.day == 1)
      return true;
   return false;
  }

string JsonField(const string obj, const string key)
  {
   string k = "\"" + key + "\":";
   int p = StringFind(obj, k);
   if(p < 0)
      return "";
   p += StringLen(k);
   int len = StringLen(obj);
   while(p < len && StringGetCharacter(obj, p) == ' ')
      p++;
   if(p >= len || StringGetCharacter(obj, p) != '"')
      return "";
   int q = StringFind(obj, "\"", p + 1);
   if(q < 0)
      return "";
   return StringSubstr(obj, p + 1, q - p - 1);
  }

datetime ParseIsoToGMT(string s)
  {
   if(StringLen(s) < 19)
      return 0;
   string base = StringSubstr(s, 0, 10) + " " + StringSubstr(s, 11, 8);
   StringReplace(base, "-", ".");
   datetime t = StringToTime(base);
   if(StringLen(s) >= 25)
     {
      int sign = (StringGetCharacter(s, 19) == '-') ? -1 : 1;
      int oh   = (int)StringToInteger(StringSubstr(s, 20, 2));
      int om   = (int)StringToInteger(StringSubstr(s, 23, 2));
      t -= sign * (oh * 3600 + om * 60);
     }
   return t;
  }

void FetchNews()
  {
   g_newsAttempt = TimeCurrent();
   char   post[], res[];
   string respHeaders;
   ResetLastError();
   int code = WebRequest("GET", NEWS_URL, "", 5000, post, res, respHeaders);
   if(code == -1)
     {
      int err = GetLastError();
      if(err == 4014)
         g_newsWebOK = false;
      Print("News feed request failed, error ", err,
            err == 4014 ? " (add https://nfs.faireconomy.media to Tools > Options > Expert Advisors > Allow WebRequest)" : "");
      return;
     }
   g_newsWebOK = true;
   if(code != 200)
     {
      Print("News feed HTTP ", code);
      return;
     }

   string json = CharArrayToString(res, 0, WHOLE_ARRAY, CP_UTF8);
   NewsEvent tmp[];
   int pos = 0;
   while(true)
     {
      int s = StringFind(json, "{", pos);
      if(s < 0) break;
      int e = StringFind(json, "}", s);
      if(e < 0) break;
      string obj = StringSubstr(json, s, e - s + 1);
      pos = e + 1;

      if(JsonField(obj, "impact") != "High") continue;
      string ccy = JsonField(obj, "country");
      if(!CurrencyWatched(ccy)) continue;
      datetime g = ParseIsoToGMT(JsonField(obj, "date"));
      if(g == 0) continue;

      int n = ArraySize(tmp);
      ArrayResize(tmp, n + 1);
      tmp[n].gmt   = g;
      tmp[n].ccy   = ccy;
      tmp[n].title = JsonField(obj, "title");
     }
   int cnt = ArraySize(tmp);
   ArrayResize(g_news, cnt);
   for(int i = 0; i < cnt; i++)
      g_news[i] = tmp[i];
   g_newsFetched = TimeCurrent();
   PrintFormat("News feed loaded: %d high-impact events", ArraySize(g_news));
  }

void UpdateGuards()
  {
   datetime now = TimeCurrent();

   datetime today = now - (now % 86400);
   if(today != g_holidayDay)
     {
      g_holidayDay = today;
      g_holiday    = FixedHoliday(now);
      if(!g_isTester && !g_holiday)
        {
         MqlCalendarValue vals[];
         int n = CalendarValueHistory(vals, today, today + 86400);
         for(int i = 0; i < n && !g_holiday; i++)
           {
            MqlCalendarEvent ev;
            MqlCalendarCountry c;
            if(!CalendarEventById(vals[i].event_id, ev)) continue;
            if(ev.type != CALENDAR_TYPE_HOLIDAY) continue;
            if(!CalendarCountryById(ev.country_id, c)) continue;
            if(CurrencyWatched(c.currency))
               g_holiday = true;
           }
        }
     }

   g_newsActive = false;
   if(!InpNewsGuard || g_isTester)
      return;

   bool stale = (now - g_newsFetched >= NEWS_REFRESH_SEC);
   if(stale && now - g_newsAttempt >= NEWS_RETRY_SEC)
      FetchNews();

   datetime gmt = TimeGMT();
   for(int i = 0; i < ArraySize(g_news); i++)
     {
      if(gmt >= g_news[i].gmt - InpNewsBefore * 60 && gmt <= g_news[i].gmt + InpNewsAfter * 60)
        {
         g_newsActive = true;
         g_newsInfo   = g_news[i].ccy + " " + g_news[i].title;
         break;
        }
     }
  }

bool ProtectionBlock()
  {
   if(FridayCloseActive())
     {
      g_status = "WEEKEND OFF";
      CloseAllPositions();
      DeleteAllPendings();
      return true;
     }
   if(InpCancelOnHolidays && g_holiday)
     {
      g_status = "HOLIDAY";
      DeleteAllPendings();
      return true;
     }
   if(g_newsActive)
     {
      g_status = "NEWS PAUSE";
      DeleteAllPendings();
      return true;
     }
   if(!InSession())
     {
      g_status = "WAITING SESSION";
      if(InpCancelOutside)
         DeleteAllPendings();
      return false;
     }
   if(InpPauseAutoWhenManual && HasManualExposure())
      g_status = "MANUAL TRAIL";
   else
      g_status = "RUNNING";
   return false;
  }

double Buf(int handle, int shift)
  {
   double v[];
   if(CopyBuffer(handle, 0, shift, 1, v) != 1)
      return EMPTY_VALUE;
   return v[0];
  }

int GetTrend()
  {
   double fast     = Buf(hEmaFast, 1);
   double slow     = Buf(hEmaSlow, 1);
   double slowPrev = Buf(hEmaSlow, 6);
   double close1   = iClose(_Symbol, InpSignalTF, 1);
   if(fast == EMPTY_VALUE || slow == EMPTY_VALUE || slowPrev == EMPTY_VALUE || close1 == 0)
      return 0;
   if(close1 > slow && fast > slow && slow >= slowPrev)
      return 1;
   if(close1 < slow && fast < slow && slow <= slowPrev)
      return -1;
   return 0;
  }

bool FindSwing(bool high, double &price)
  {
   int n = InpSwingStrength;
   for(int i = n + 1; i <= InpSwingLookback; i++)
     {
      double v = high ? iHigh(_Symbol, InpSignalTF, i) : iLow(_Symbol, InpSignalTF, i);
      bool ok = true;
      for(int k = 1; k <= n && ok; k++)
        {
         double l = high ? iHigh(_Symbol, InpSignalTF, i - k) : iLow(_Symbol, InpSignalTF, i - k);
         double r = high ? iHigh(_Symbol, InpSignalTF, i + k) : iLow(_Symbol, InpSignalTF, i + k);
         if(high  && (l >= v || r > v)) ok = false;
         if(!high && (l <= v || r < v)) ok = false;
        }
      if(!ok)
         continue;
      bool broken = false;
      for(int j = 0; j < i && !broken; j++)
        {
         if(high  && iHigh(_Symbol, InpSignalTF, j) > v) broken = true;
         if(!high && iLow(_Symbol, InpSignalTF, j)  < v) broken = true;
        }
      if(broken)
         continue;
      price = v;
      return true;
     }
   return false;
  }

bool VolumeOK()
  {
   if(!InpVolumeFilter)
      return true;
   long vols[];
   if(CopyTickVolume(_Symbol, InpSignalTF, 1, InpVolumePeriod + 1, vols) != InpVolumePeriod + 1)
      return false;
   double sum = 0;
   for(int i = 0; i < InpVolumePeriod; i++)
      sum += (double)vols[i];
   double avg = sum / InpVolumePeriod;
   return (double)vols[InpVolumePeriod] >= avg * InpVolumeMult;
  }

bool MomentumOK(int dir)
  {
   if(!InpMomentumFilter)
      return true;
   double r1 = Buf(hRsi, 1);
   double r2 = Buf(hRsi, 2);
   if(r1 == EMPTY_VALUE || r2 == EMPTY_VALUE)
      return false;
   if(dir > 0) return r1 > 50.0 && r1 >= r2;
   return r1 < 50.0 && r1 <= r2;
  }

bool CandleOK(int dir)
  {
   if(!InpCandleFilter)
      return true;
   double o = iOpen(_Symbol, InpSignalTF, 1);
   double c = iClose(_Symbol, InpSignalTF, 1);
   double h = iHigh(_Symbol, InpSignalTF, 1);
   double l = iLow(_Symbol, InpSignalTF, 1);
   double range = h - l;
   if(range <= 0)
      return false;
   if(MathAbs(c - o) / range < InpMinBodyRatio)
      return false;
   return dir > 0 ? c > o : c < o;
  }

bool ExtensionOK(double entry)
  {
   if(!InpExtensionFilter || entry <= 0 || InpMaxEmaDistAtr <= 0)
      return true;
   double ema = Buf(hEmaFast, 1);
   double atr = Buf(hAtr, 1);
   if(ema == EMPTY_VALUE || atr == EMPTY_VALUE || atr <= 0)
      return false;
   return MathAbs(entry - ema) <= atr * InpMaxEmaDistAtr;
  }

bool VolatilityOK()
  {
   if(InpMinAtrUsd <= 0)
      return true;
   double atr = Buf(hAtr, 1);
   if(atr == EMPTY_VALUE || atr <= 0)
      return false;
   return atr / _Point >= UsdToPoints(InpMinAtrUsd);
  }

int SpreadPoints()
  {
   return (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
  }

bool CooldownOK()
  {
   if(InpCooldownBars <= 0 || g_lastCloseTime == 0)
      return true;
   return TimeCurrent() - g_lastCloseTime >= InpCooldownBars * PeriodSeconds(InpSignalTF);
  }

double BuyLevel()
  {
   double sh;
   if(!FindSwing(true, sh))
      return 0;
   double ask    = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double minGap = (SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) + SpreadPoints() + 5) * _Point;
   double entry  = NormalizePrice(sh + g_bufferPts * _Point);
   if(entry - ask < minGap || entry - ask > g_maxEntryPts * _Point)
      return 0;
   return entry;
  }

double SellLevel()
  {
   double sl;
   if(!FindSwing(false, sl))
      return 0;
   double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double minGap = (SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) + SpreadPoints() + 5) * _Point;
   double entry  = NormalizePrice(sl - g_bufferPts * _Point);
   if(bid - entry < minGap || bid - entry > g_maxEntryPts * _Point)
      return 0;
   return entry;
  }

void EvaluateSignal()
  {
   g_trend = GetTrend();
   if(HasPosition())
      return;
   if(InpPauseAutoWhenManual && HasManualExposure())
     {
      DeleteAllPendings();
      return;
     }

   bool allowBuy  = !InpTrendFilter || g_trend > 0 || (g_trend == 0 && InpNeutralBothSides);
   bool allowSell = !InpTrendFilter || g_trend < 0 || (g_trend == 0 && InpNeutralBothSides);

   double buyEntry  = allowBuy  ? BuyLevel()  : 0;
   double sellEntry = allowSell ? SellLevel() : 0;
   if(!ExtensionOK(buyEntry))  buyEntry  = 0;
   if(!ExtensionOK(sellEntry)) sellEntry = 0;

   bool common = InSession()
                 && SpreadPoints() <= g_maxSpreadPts
                 && g_tradesToday < InpMaxTradesPerDay
                 && CooldownOK()
                 && VolumeOK()
                 && VolatilityOK();

   HandleSide(ORDER_TYPE_BUY_STOP,  buyEntry,  common && MomentumOK(1)  && CandleOK(1));
   HandleSide(ORDER_TYPE_SELL_STOP, sellEntry, common && MomentumOK(-1) && CandleOK(-1));
  }

void HandleSide(ENUM_ORDER_TYPE type, double entry, bool canPlace)
  {
   ulong  ticket = 0;
   double price  = 0;
   bool   has    = GetPendingOfType(type, ticket, price);

   if(entry <= 0)
     {
      if(has)
         trade.OrderDelete(ticket);
      return;
     }
   if(has && MathAbs(price - entry) < _Point)
     {
      if(InpDynamicTP && OrderSelect(ticket))
        {
         int    dir   = type == ORDER_TYPE_BUY_STOP ? 1 : -1;
         double curTP = OrderGetDouble(ORDER_TP);
         double newTP = NormalizePrice(price + dir * TpPointsNow() * _Point);
         if(MathAbs(curTP - newTP) >= _Point)
            trade.OrderModify(ticket, price, OrderGetDouble(ORDER_SL), newTP, ORDER_TIME_GTC, 0);
        }
      return;
     }
   if(!canPlace)
      return;
   if(has)
      trade.OrderDelete(ticket);
   PlacePending(type == ORDER_TYPE_BUY_STOP ? 1 : -1, entry);
  }

double NormalizePrice(double p)
  {
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(ts > 0)
      p = MathRound(p / ts) * ts;
   return NormalizeDouble(p, _Digits);
  }

double NormalizeLot(double lot)
  {
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vlim = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_LIMIT);
   if(vlim > 0) vmax = MathMin(vmax, vlim);
   if(step <= 0) step = 0.01;
   lot = MathFloor(lot / step) * step;
   lot = MathMax(vmin, MathMin(vmax, lot));
   return NormalizeDouble(lot, 2);
  }

double CalcLot(int dir, double entry, double sl)
  {
   if(InpUseFixedLot)
      return NormalizeLot(InpFixedLot);

   ENUM_ORDER_TYPE mt = dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double riskMoney  = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;
   double lossPerLot = 0;
   if(!OrderCalcProfit(mt, _Symbol, 1.0, entry, sl, lossPerLot) || lossPerLot == 0)
     {
      double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      if(tv <= 0 || ts <= 0) return NormalizeLot(0);
      lossPerLot = MathAbs(entry - sl) / ts * tv;
     }
   lossPerLot = MathAbs(lossPerLot);
   if(lossPerLot <= 0)
      return NormalizeLot(0);

   double lot = riskMoney / lossPerLot;

   double marginPerLot = 0;
   if(OrderCalcMargin(mt, _Symbol, 1.0, entry, marginPerLot) && marginPerLot > 0)
     {
      double maxByMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.9 / marginPerLot;
      lot = MathMin(lot, maxByMargin);
     }
   return NormalizeLot(lot);
  }

int UsdToPoints(double usd)
  {
   double ts  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tv  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double ref = InpRefLot > 0 ? InpRefLot : 0.01;
   if(usd <= 0 || ts <= 0 || tv <= 0 || _Point <= 0)
      return 0;
   return (int)MathRound(usd * ts / (tv * ref) / _Point);
  }

int TpPointsNow()
  {
   if(!InpDynamicTP)
      return g_tpPts;
   double adx = Buf(hAdx, 1);
   double usd = InpTP1Usd;
   if(adx != EMPTY_VALUE)
     {
      if(adx >= InpADXLevel6)      usd = InpTP6Usd;
      else if(adx >= InpADXLevel5) usd = InpTP5Usd;
      else if(adx >= InpADXLevel4) usd = InpTP4Usd;
      else if(adx >= InpADXLevel3) usd = InpTP3Usd;
      else if(adx >= InpADXLevel2) usd = InpTP2Usd;
     }
   int pts = UsdToPoints(usd);
   return pts > 0 ? pts : g_tpPts;
  }

int SlPointsNow()
  {
   if(!InpAtrStops)
      return g_slPts;
   double atr = Buf(hAtr, 1);
   if(atr == EMPTY_VALUE || atr <= 0)
      return g_slPts;
   int pts = (int)MathRound(atr * InpAtrSLMult / _Point);
   int lo  = UsdToPoints(InpAtrSLMinUsd);
   int hi  = UsdToPoints(InpAtrSLMaxUsd);
   if(lo > 0) pts = MathMax(pts, lo);
   if(hi > 0) pts = MathMin(pts, hi);
   return pts > 0 ? pts : g_slPts;
  }

int PositionSlPts(ulong posId, bool buy, double open, double curSL)
  {
   if(posId == g_posId && g_posSlPts > 0)
      return g_posSlPts;
   if(curSL > 0 && (buy ? curSL < open : curSL > open))
      return (int)MathRound(MathAbs(open - curSL) / _Point);
   return SlPointsNow();
  }

void PlacePending(int dir, double entry)
  {
   double pt = _Point;
   int slPts = SlPointsNow();
   double sl = NormalizePrice(dir > 0 ? entry - slPts * pt : entry + slPts * pt);
   int tpPts = TpPointsNow();
   double tp = NormalizePrice(dir > 0 ? entry + tpPts * pt : entry - tpPts * pt);
   double lot = CalcLot(dir, entry, sl);
   g_nextLot = lot;

   bool ok;
   if(dir > 0)
      ok = trade.BuyStop(lot, entry, _Symbol, sl, tp, ORDER_TIME_GTC, 0, InpComment);
   else
      ok = trade.SellStop(lot, entry, _Symbol, sl, tp, ORDER_TIME_GTC, 0, InpComment);

   if(!ok)
     {
      CheckMarketClosed();
      PrintFormat("Pending %s failed: %d %s", dir > 0 ? "BUY STOP" : "SELL STOP",
                  trade.ResultRetcode(), trade.ResultRetcodeDescription());
     }
   else
      Log(StringFormat("%s %.2f @ %.2f SL %.2f TP %.2f", dir > 0 ? "BUY STOP" : "SELL STOP", lot, entry, sl, tp));
  }

bool IsChartSymbolPos()
  {
   return PositionGetString(POSITION_SYMBOL) == _Symbol;
  }

bool IsEaPosition()
  {
   return PositionGetInteger(POSITION_MAGIC) == InpMagic && IsChartSymbolPos();
  }

bool IsManualPosition()
  {
   return InpManageManual && PositionGetInteger(POSITION_MAGIC) == 0 && IsChartSymbolPos();
  }

bool IsManagedPosition()
  {
   return IsEaPosition() || IsManualPosition();
  }

bool IsOurPosition()
  {
   return IsEaPosition();
  }

bool IsOurOrder()
  {
   return OrderGetInteger(ORDER_MAGIC) == InpMagic && OrderGetString(ORDER_SYMBOL) == _Symbol;
  }

bool IsManualPending()
  {
   if(!InpManageManual)
      return false;
   if(OrderGetString(ORDER_SYMBOL) != _Symbol)
      return false;
   if(OrderGetInteger(ORDER_MAGIC) != 0)
      return false;
   ENUM_ORDER_TYPE typ = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
   return (typ == ORDER_TYPE_BUY_STOP || typ == ORDER_TYPE_SELL_STOP
           || typ == ORDER_TYPE_BUY_LIMIT || typ == ORDER_TYPE_SELL_LIMIT
           || typ == ORDER_TYPE_BUY_STOP_LIMIT || typ == ORDER_TYPE_SELL_STOP_LIMIT);
  }

bool HasManualExposure()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(PositionGetTicket(i) > 0 && IsManualPosition())
         return true;
     }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(OrderGetTicket(i) > 0 && IsManualPending())
         return true;
     }
   return false;
  }

bool HasPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(PositionGetTicket(i) > 0 && IsOurPosition())
         return true;
   return false;
  }

bool GetPendingOfType(ENUM_ORDER_TYPE type, ulong &ticket, double &price)
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0 || !IsOurOrder()) continue;
      if((ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) != type) continue;
      ticket = t;
      price  = OrderGetDouble(ORDER_PRICE_OPEN);
      return true;
     }
   return false;
  }

bool HasPending()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
      if(OrderGetTicket(i) > 0 && IsOurOrder())
         return true;
   return false;
  }

bool MarketBlocked()
  {
   return TimeCurrent() < g_marketClosedUntil;
  }

void CheckMarketClosed()
  {
   if(trade.ResultRetcode() == TRADE_RETCODE_MARKET_CLOSED)
      g_marketClosedUntil = TimeCurrent() + 60;
  }

void DeleteAllPendings()
  {
   if(MarketBlocked()) return;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0 || !IsOurOrder()) continue;
      if(!trade.OrderDelete(t))
        {
         CheckMarketClosed();
         if(MarketBlocked()) return;
        }
     }
  }

void CloseAllPositions()
  {
   if(MarketBlocked()) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !IsOurPosition()) continue;
      if(!trade.PositionClose(t))
        {
         CheckMarketClosed();
         if(MarketBlocked()) return;
        }
     }
  }

void ManagePendingExpiry()
  {
   if(HasPosition())
     {
      DeleteAllPendings();
      return;
     }
   int maxAge = InpPendingExpiryBars * PeriodSeconds(InpSignalTF);
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0 || !IsOurOrder()) continue;
      datetime setup = (datetime)OrderGetInteger(ORDER_TIME_SETUP);
      if(TimeCurrent() - setup >= maxAge)
        {
         Log("Pending expired: " + IntegerToString((long)t));
         if(!trade.OrderDelete(t))
           {
            CheckMarketClosed();
            if(MarketBlocked()) return;
           }
        }
     }
  }

void ApplyTrail(const bool buy, const double bid, const double ask, const double stopLevel,
                const double pt, const int trStart, const int trDist, const int trStep,
                double &newSL)
  {
   if(!InpUseTrailing)
      return;
   double profitPts = buy ? (bid - PositionGetDouble(POSITION_PRICE_OPEN)) / pt
                          : (PositionGetDouble(POSITION_PRICE_OPEN) - ask) / pt;
   if(profitPts < trStart)
      return;
   // Start at +$0.50 with original Thunder 70-pt / $0.70 distance: SL may sit below BE at first.
   double dist = MathMax(trDist * pt, stopLevel + pt);
   if(buy)
     {
      double cand = NormalizePrice(bid - dist);
      if(cand > bid - stopLevel - pt)
         return;
      if(newSL > 0 && cand <= newSL)
         return;
      if(newSL > 0 && cand < newSL + trStep * pt)
         return;
      newSL = cand;
     }
   else
     {
      double cand = NormalizePrice(ask + dist);
      if(cand < ask + stopLevel + pt)
         return;
      if(newSL > 0 && cand >= newSL)
         return;
      if(newSL > 0 && cand > newSL - trStep * pt)
         return;
      newSL = cand;
     }
  }

void ManagePositions()
  {
   double pt        = _Point;
   double stopLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * pt;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !IsManagedPosition()) continue;

      bool   manual = IsManualPosition();
      bool   buy    = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
      double open   = PositionGetDouble(POSITION_PRICE_OPEN);
      double curSL  = PositionGetDouble(POSITION_SL);
      double curTP  = PositionGetDouble(POSITION_TP);
      double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask    = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double newSL  = curSL, newTP = curTP;

      ulong posId = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      int   slPts = PositionSlPts(posId, buy, open, curSL);
      int   trStart = g_trailStart, trDist = g_trailDist, trStep = g_trailStep;
      if(InpAtrStops && !manual)
        {
         trStart = (int)MathRound(slPts * InpTrailStartR);
         trDist  = (int)MathRound(slPts * InpTrailDistR);
         trStep  = MathMax(1, (int)MathRound(slPts * InpTrailStepR));
        }

      double baseSL = NormalizePrice(buy ? open - slPts * pt : open + slPts * pt);
      double baseTP = NormalizePrice(buy ? open + g_tpPts * pt : open - g_tpPts * pt);

      if(!manual && g_reanchorPos != 0 && posId == g_reanchorPos)
        {
         int tpPts = g_reanchorTpPts > 0 ? g_reanchorTpPts : g_tpPts;
         newSL = baseSL;
         newTP = NormalizePrice(buy ? open + tpPts * pt : open - tpPts * pt);
         g_reanchorPos = 0;
         g_reanchorTpPts = 0;
        }

      if(!manual || !InpManualKeepStops)
        {
         if(newSL == 0) newSL = baseSL;
         if(newTP == 0) newTP = baseTP;
        }

      double profitPts = buy ? (bid - open) / pt : (open - ask) / pt;
      if(!manual && InpBreakevenUsd > 0 && profitPts >= InpBreakevenUsd / pt)
        {
         double lock = InpBreakevenLockPts * g_pf * pt;
         if(buy)
           {
            double cand = NormalizePrice(open + lock);
            if(cand > newSL && cand <= bid - stopLevel - pt)
               newSL = cand;
           }
         else
           {
            double cand = NormalizePrice(open - lock);
            if((newSL == 0 || cand < newSL) && cand >= ask + stopLevel + pt)
               newSL = cand;
           }
        }

      ApplyTrail(buy, bid, ask, stopLevel, pt, trStart, trDist, trStep, newSL);

      if(newSL != curSL || newTP != curTP)
        {
         if(!trade.PositionModify(t, newSL, newTP))
           {
            Log(StringFormat("Modify failed: %d", trade.ResultRetcode()));
            CheckMarketClosed();
            if(MarketBlocked()) return;
           }
        }
     }
  }

void RecalcStats()
  {
   g_profitDay = g_profitMonth = g_profitTotal = 0;
   g_grossProfit = g_grossLoss = 0;
   g_wins = g_losses = g_tradesToday = 0;

   datetime now = TimeCurrent();
   MqlDateTime d;
   TimeToStruct(now, d);
   datetime dayStart = now - (now % 86400);
   g_statsDay = dayStart;
   d.day = 1; d.hour = 0; d.min = 0; d.sec = 0;
   datetime monthStart = StructToTime(d);

   if(!HistorySelect(0, now + 60))
      return;
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong dl = HistoryDealGetTicket(i);
      if(dl == 0) continue;
      if(HistoryDealGetInteger(dl, DEAL_MAGIC) != InpMagic) continue;
      if(HistoryDealGetString(dl, DEAL_SYMBOL) != _Symbol) continue;

      datetime t = (datetime)HistoryDealGetInteger(dl, DEAL_TIME);
      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(dl, DEAL_ENTRY);
      double net = HistoryDealGetDouble(dl, DEAL_PROFIT)
                   + HistoryDealGetDouble(dl, DEAL_SWAP)
                   + HistoryDealGetDouble(dl, DEAL_COMMISSION);

      g_profitTotal += net;
      if(t >= monthStart) g_profitMonth += net;
      if(t >= dayStart)   g_profitDay   += net;

      if(entry == DEAL_ENTRY_IN)
        {
         if(t >= dayStart) g_tradesToday++;
         continue;
        }
      if(t > g_lastCloseTime) g_lastCloseTime = t;
      if(net >= 0) { g_wins++;   g_grossProfit += net; }
      else         { g_losses++; g_grossLoss   -= net; }
     }
  }

void DrawClosedLabel(ulong deal, datetime t, double price, double net)
  {
   string n = PFX + "PNL_" + IntegerToString((long)deal);
   if(ObjectFind(0, n) < 0)
      ObjectCreate(0, n, OBJ_TEXT, 0, t, price);
   ObjectSetString(0, n, OBJPROP_TEXT, StringFormat("%s%.2f USD", net >= 0 ? "+" : "", net));
   ObjectSetString(0, n, OBJPROP_FONT, "Segoe UI Semibold");
   ObjectSetInteger(0, n, OBJPROP_FONTSIZE, 11);
   ObjectSetInteger(0, n, OBJPROP_COLOR, net >= 0 ? CLR_GOLD : CLR_MUTED);
   ObjectSetInteger(0, n, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, n, OBJPROP_HIDDEN, true);
  }

void DrawFloatingLabel()
  {
   string n = PFX + "FLOAT";
   double floating = 0;
   bool   found = false;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(PositionGetTicket(i) == 0 || !IsManagedPosition()) continue;
      floating += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      found = true;
     }
   if(!InpShowPnLLabels || !found)
     {
      ObjectDelete(0, n);
      return;
     }
   datetime t = iTime(_Symbol, PERIOD_CURRENT, 0);
   double   p = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ObjectFind(0, n) < 0)
      ObjectCreate(0, n, OBJ_TEXT, 0, t, p);
   ObjectMove(0, n, 0, t, p);
   ObjectSetString(0, n, OBJPROP_TEXT, StringFormat("   %s%.2f USD", floating >= 0 ? "+" : "", floating));
   ObjectSetString(0, n, OBJPROP_FONT, "Segoe UI Semibold");
   ObjectSetInteger(0, n, OBJPROP_FONTSIZE, 10);
   ObjectSetInteger(0, n, OBJPROP_COLOR, floating >= 0 ? CLR_GREEN : CLR_RED);
   ObjectSetInteger(0, n, OBJPROP_ANCHOR, ANCHOR_LEFT);
   ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, n, OBJPROP_HIDDEN, true);
  }

void DrawNewsWarning()
  {
   string n = PFX + "NEWSWARN";
   if(!InpNewsGuard || g_isTester || g_newsWebOK)
     {
      ObjectDelete(0, n);
      return;
     }
   if(ObjectFind(0, n) < 0)
     {
      ObjectCreate(0, n, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, n, OBJPROP_CORNER, CORNER_LEFT_LOWER);
      ObjectSetInteger(0, n, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
      ObjectSetInteger(0, n, OBJPROP_XDISTANCE, 15);
      ObjectSetInteger(0, n, OBJPROP_YDISTANCE, 20);
      ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, n, OBJPROP_HIDDEN, true);
      ObjectSetString(0, n, OBJPROP_FONT, "Segoe UI Semibold");
      ObjectSetInteger(0, n, OBJPROP_FONTSIZE, 10);
      ObjectSetInteger(0, n, OBJPROP_COLOR, CLR_RED);
     }
   ObjectSetString(0, n, OBJPROP_TEXT,
                   "NEWS FILTER INACTIVE: Allow WebRequest for https://nfs.faireconomy.media");
  }

int S(double v) { return (int)MathRound(v * g_scale); }

void HRect(string id, double x, double y, double w, double h, color bg, color border)
  {
   string n = PFX + id;
   if(ObjectFind(0, n) < 0)
     {
      ObjectCreate(0, n, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, n, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, n, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, n, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, n, OBJPROP_BACK, false);
      ObjectSetInteger(0, n, OBJPROP_WIDTH, 1);
     }
   ObjectSetInteger(0, n, OBJPROP_XDISTANCE, InpPanelX + S(x));
   ObjectSetInteger(0, n, OBJPROP_YDISTANCE, InpPanelY + S(y));
   ObjectSetInteger(0, n, OBJPROP_XSIZE, MathMax(1, S(w)));
   ObjectSetInteger(0, n, OBJPROP_YSIZE, MathMax(1, S(h)));
   ObjectSetInteger(0, n, OBJPROP_BGCOLOR, bg);
   ObjectSetInteger(0, n, OBJPROP_COLOR, border);
  }

void HText(string id, double x, double y, string txt, int size, color clr,
           bool bold = false, ENUM_ANCHOR_POINT anchor = ANCHOR_LEFT_UPPER)
  {
   string n = PFX + id;
   if(ObjectFind(0, n) < 0)
     {
      ObjectCreate(0, n, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, n, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, n, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, n, OBJPROP_BACK, false);
     }
   ObjectSetInteger(0, n, OBJPROP_XDISTANCE, InpPanelX + S(x));
   ObjectSetInteger(0, n, OBJPROP_YDISTANCE, InpPanelY + S(y));
   ObjectSetInteger(0, n, OBJPROP_ANCHOR, anchor);
   ObjectSetString(0, n, OBJPROP_FONT, bold ? "Segoe UI Semibold" : "Segoe UI");
   ObjectSetInteger(0, n, OBJPROP_FONTSIZE, MathMax(5, (int)MathRound(size * g_scale)));
   ObjectSetInteger(0, n, OBJPROP_COLOR, clr);
   ObjectSetString(0, n, OBJPROP_TEXT, txt);
  }

void HField(string id, double x, double y, string caption, string value, color valClr)
  {
   HText(id + "_c", x, y, caption, 7, CLR_GOLD, true);
   HText(id + "_v", x, y + 16, value, 9, valClr, true);
  }

void HRow(string id, double x, double y, double w, string caption, string value, color valClr)
  {
   HText(id + "_c", x, y, caption, 7, CLR_MUTED);
   HText(id + "_v", x + w, y, value, 8, valClr, true, ANCHOR_RIGHT_UPPER);
  }

void HFilter(string id, double x, double y, double w, string caption, bool on, string value)
  {
   HRect(id + "_dot", x, y + 3, 8, 8, on ? CLR_GREEN : CLR_MUTED, on ? CLR_GREEN : CLR_MUTED);
   HText(id + "_c", x + 14, y, caption, 7, CLR_TEXT);
   HText(id + "_v", x + w, y, value, 7, on ? CLR_GREEN : CLR_MUTED, true, ANCHOR_RIGHT_UPPER);
  }

string Money(double v, bool sign = false)
  {
   string s = DoubleToString(MathAbs(v), 2);
   if(v < 0) return "-" + s + " USD";
   return (sign && v > 0 ? "+" : "") + s + " USD";
  }

void UpdateScale()
  {
   const double BASE_W = 520, BASE_H = 470;
   if(InpPanelScale > 0)
     {
      g_scale = MathMax(0.4, MathMin(1.0, InpPanelScale));
      return;
     }
   double cw = (double)ChartGetInteger(0, CHART_WIDTH_IN_PIXELS);
   double ch = (double)ChartGetInteger(0, CHART_HEIGHT_IN_PIXELS);
   if(cw <= 0 || ch <= 0) { g_scale = 1.0; return; }
   g_scale = MathMin(cw * 0.40 / BASE_W, ch * 0.80 / BASE_H);
   g_scale = MathMax(0.4, MathMin(1.0, g_scale));
  }

void DrawHUD()
  {
   UpdateScale();

   double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity   = AccountInfoDouble(ACCOUNT_EQUITY);
   double floating = equity - balance;
   double fltPct   = balance > 0 ? floating / balance * 100.0 : 0;

   if(g_nextLot <= 0 || (!HasPosition() && !HasPending()))
     {
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      if(ask > 0)
         g_nextLot = CalcLot(1, ask, ask - SlPointsNow() * _Point);
     }

   string trendTxt = g_trend > 0 ? "BULLISH" : (g_trend < 0 ? "BEARISH" : "NEUTRAL");
   color  trendClr = g_trend > 0 ? CLR_GREEN : (g_trend < 0 ? CLR_RED : CLR_TEXT);
   bool   manualOn = InpPauseAutoWhenManual && HasManualExposure();

   int    closed  = g_wins + g_losses;
   string winRate = closed > 0 ? DoubleToString(100.0 * g_wins / closed, 1) + "%" : "---";
   double pfVal   = g_grossLoss > 0 ? g_grossProfit / g_grossLoss : (g_grossProfit > 0 ? 99 : 0);
   string slip    = g_lastSlippage >= 0 ? IntegerToString((int)MathRound(g_lastSlippage)) + " pts" : "---";

   HRect("bg", 0, 0, 520, 470, CLR_BG, CLR_GOLD);
   HText("logo", 16, 12, BOLT, 22, CLR_GOLD, true);
   HText("title", 50, 14, "JM THUNDER GOLD SCALPER", 12, CLR_GOLD, true);
   HText("sub", 50, 36, "STRUCTURE. MOMENTUM. PRECISION.", 7, CLR_GOLD_DIM, true);
   HRect("badge", 428, 12, 78, 34, CLR_BOX, CLR_GOLD_DIM);
   HText("badge_t", 467, 20, "JM " + BOLT + " v2.0.3", 7, CLR_GOLD, true, ANCHOR_UPPER);
   HRect("hline", 10, 56, 500, 1, CLR_GOLD_DIM, CLR_GOLD_DIM);

   HRect("acc", 10, 66, 370, 128, CLR_BOX, CLR_GOLD_DIM);
   HField("bal", 22, 76, "BALANCE", Money(balance), CLR_TEXT);
   HField("eq", 145, 76, "EQUITY", Money(equity), CLR_GREEN);
   HField("flt", 265, 76, "FLOATING P&L", Money(floating, true), floating >= 0 ? CLR_GREEN : CLR_RED);
   HText("flt_p", 265, 108, StringFormat("(%.2f%%)", fltPct), 7, floating >= 0 ? CLR_GREEN : CLR_RED);
   HRect("acc_l", 20, 128, 350, 1, CLR_GOLD_DIM, CLR_GOLD_DIM);
   HField("spr", 22, 140, "SPREAD", IntegerToString(SpreadPoints()) + " pts",
          SpreadPoints() <= g_maxSpreadPts ? CLR_GREEN : CLR_RED);
   HField("trd", 145, 140, "TREND", trendTxt, trendClr);
   HField("rsk", 265, 140, "TRAIL",
          StringFormat("$%.2f / $%.2f", InpTrailStartUsd, InpTrailDistanceUsd), CLR_TEXT);

   HRect("exe", 390, 66, 120, 334, CLR_BOX, CLR_GOLD_DIM);
   HText("exe_t", 400, 76, "EXECUTION", 8, CLR_GOLD, true);
   HText("ex1_c", 400, 100, "TRADES TODAY", 6, CLR_MUTED);
   HText("ex1_v", 400, 113, StringFormat("%d / %d", g_tradesToday, InpMaxTradesPerDay), 10, CLR_TEXT, true);
   HText("ex2_c", 400, 145, "LOT SIZE", 6, CLR_MUTED);
   HText("ex2_v", 400, 158, DoubleToString(g_nextLot, 2) + " lot", 10, CLR_TEXT, true);
   HText("ex3_c", 400, 190, "WIN RATE", 6, CLR_MUTED);
   HText("ex3_v", 400, 203, winRate, 10, CLR_GREEN, true);
   HText("ex4_c", 400, 235, "LAST SLIPPAGE", 6, CLR_MUTED);
   HText("ex4_v", 400, 248, slip, 10, CLR_TEXT, true);
   HText("ex5_c", 400, 280, "MANUAL", 6, CLR_MUTED);
   HText("ex5_v", 400, 293, manualOn ? "TRAILING" : (InpManageManual ? "READY" : "OFF"), 10,
         manualOn ? CLR_GOLD : CLR_TEXT, true);
   HText("ex6_c", 400, 325, "SYSTEM", 6, CLR_MUTED);
   HText("ex6_v", 400, 338, g_status, 8, g_status == "RUNNING" ? CLR_GREEN : CLR_GOLD, true);

   string newsState = !InpNewsGuard ? "OFF"
                      : (g_isTester ? "N/A" : (!g_newsWebOK ? "NO URL" : (g_newsActive ? "PAUSED" : "CLEAR")));
   HRect("news", 10, 204, 175, 86, CLR_BOX, CLR_GOLD_DIM);
   HText("news_t", 20, 214, "NEWS GUARD", 8, CLR_GOLD, true);
   HText("news_s", 175, 212, newsState, 10, (g_newsActive || !g_newsWebOK) ? CLR_RED : CLR_TEXT, true, ANCHOR_RIGHT_UPPER);
   HRow("nw1", 20, 240, 155, "WINDOW", StringFormat("%d / %d min", InpNewsBefore, InpNewsAfter), CLR_TEXT);
   HRow("nw2", 20, 262, 155, "CCY", InpNewsCurrencies == "" ? "ALL" : InpNewsCurrencies, CLR_TEXT);

   HRect("prot", 195, 204, 185, 86, CLR_BOX, CLR_GOLD_DIM);
   HText("prot_t", 370, 214, "PROTECTION", 8, CLR_GOLD, true, ANCHOR_RIGHT_UPPER);
   HRow("pr1", 205, 234, 165, "FRIDAY CLOSE",
        InpFridayClose ? StringFormat("%02d:00 GMT", InpFridayCloseHour) : "OFF", CLR_GOLD);
   HRow("pr2", 205, 252, 165, "HOLIDAY SHIELD",
        !InpCancelOnHolidays ? "OFF" : (g_holiday ? "ACTIVE" : "ARMED"), g_holiday ? CLR_RED : CLR_GREEN);
   HRow("pr3", 205, 270, 165, "MANUAL SL/TP", InpManualKeepStops ? "KEEP" : "EA", CLR_GREEN);

   HRect("flt_b", 10, 300, 370, 100, CLR_BOX, CLR_GOLD_DIM);
   HText("flt_t", 20, 308, "FILTERS & EXECUTION", 8, CLR_GOLD, true);
   bool sessOpen = InSession();
   HFilter("f1", 20, 328, 220, "TREND FILTER", InpTrendFilter, InpTrendFilter ? "ON" : "OFF");
   HFilter("f2", 20, 344, 220, "VOLUME FILTER", InpVolumeFilter, InpVolumeFilter ? "ON" : "OFF");
   HFilter("f3", 20, 360, 220, "NEWS GUARD", InpNewsGuard, InpNewsGuard ? "ON" : "OFF");
   HFilter("f4", 20, 376, 220, "TRADING SESSION", sessOpen, sessOpen ? "OPEN" : "CLOSED");
   HText("emblem", 312, 350, BOLT, 30, CLR_GOLD, true, ANCHOR_CENTER);

   HRect("foot", 10, 410, 500, 50, CLR_BOX, CLR_GOLD_DIM);
   HText("ft1_c", 70, 418, "PROFIT DAY", 6, CLR_GOLD, true, ANCHOR_UPPER);
   HText("ft1_v", 70, 436, Money(g_profitDay, true), 8, g_profitDay >= 0 ? CLR_GREEN : CLR_RED, true, ANCHOR_UPPER);
   HText("ft2_c", 195, 418, "PROFIT MONTH", 6, CLR_GOLD, true, ANCHOR_UPPER);
   HText("ft2_v", 195, 436, Money(g_profitMonth, true), 8, g_profitMonth >= 0 ? CLR_GREEN : CLR_RED, true, ANCHOR_UPPER);
   HText("ft3_c", 320, 418, "PROFIT TOTAL", 6, CLR_GOLD, true, ANCHOR_UPPER);
   HText("ft3_v", 320, 436, Money(g_profitTotal, true), 8, g_profitTotal >= 0 ? CLR_GREEN : CLR_RED, true, ANCHOR_UPPER);
   HText("ft4_c", 445, 418, "SERVER TIME", 6, CLR_GOLD, true, ANCHOR_UPPER);
   HText("ft4_v", 445, 436, TimeToString(TimeCurrent(), TIME_SECONDS), 8, CLR_TEXT, true, ANCHOR_UPPER);

   DrawFloatingLabel();
   ChartRedraw(0);
  }

struct ATrade
  {
   ulong    pos;
   bool     closed;
   datetime tOpen;
   int      dir;
   int      srvHour;
   int      phtHour;
   int      wday;
   int      trend;
   double   entry;
   double   atrUsd;
   double   rsi;
   double   adx;
   double   emaDistAtr;
   int      spread;
   double   slip;
   int      slPts;
   double   mfe;
   double   mae;
   double   net;
   double   pts;
   int      durSec;
   int      reason;
  };

struct ABucket
  {
   int    n;
   int    w;
   int    sl;
   double pts;
   double usd;
  };

ATrade g_at[];
int    g_atN = 0;

int AFind(ulong pos)
  {
   for(int i = g_atN - 1; i >= 0; i--)
      if(g_at[i].pos == pos)
         return i;
   return -1;
  }

void AnalyzerOnEntry(ulong deal, double price)
  {
   if(!InpAnalyzer)
      return;
   ulong pos = (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID);
   if(AFind(pos) >= 0)
      return;
   if(g_atN >= ArraySize(g_at))
      ArrayResize(g_at, g_atN + 500);

   ATrade t;
   ZeroMemory(t);
   t.pos    = pos;
   t.tOpen  = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
   t.dir    = HistoryDealGetInteger(deal, DEAL_TYPE) == DEAL_TYPE_BUY ? 1 : -1;
   MqlDateTime dt;
   TimeToStruct(t.tOpen, dt);
   t.srvHour = dt.hour;
   t.wday    = dt.day_of_week;
   int off   = (int)MathRound((double)(TimeCurrent() - GMTNow()) / 3600.0);
   t.phtHour = ((t.srvHour - off + 8) % 24 + 24) % 24;
   t.trend   = g_trend;
   t.entry   = price;
   double atr = Buf(hAtr, 1), rsi = Buf(hRsi, 1), adx = Buf(hAdx, 1), ema = Buf(hEmaFast, 1);
   t.atrUsd  = atr != EMPTY_VALUE ? atr : 0;
   t.rsi     = rsi != EMPTY_VALUE ? rsi : 50;
   t.adx     = adx != EMPTY_VALUE ? adx : 0;
   t.emaDistAtr = (atr != EMPTY_VALUE && atr > 0 && ema != EMPTY_VALUE) ? MathAbs(price - ema) / atr : 0;
   t.spread  = SpreadPoints();
   t.slip    = g_lastSlippage;
   t.slPts   = g_posSlPts > 0 ? g_posSlPts : g_slPts;
   g_at[g_atN++] = t;
  }

void AnalyzerTrack()
  {
   if(!InpAnalyzer || g_atN == 0)
      return;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   for(int p = PositionsTotal() - 1; p >= 0; p--)
     {
      if(PositionGetTicket(p) == 0 || !IsManagedPosition())
         continue;
      int i = AFind((ulong)PositionGetInteger(POSITION_IDENTIFIER));
      if(i < 0 || g_at[i].closed)
         continue;
      double cur = g_at[i].dir > 0 ? (bid - g_at[i].entry) : (g_at[i].entry - ask);
      cur /= _Point;
      if(cur > g_at[i].mfe) g_at[i].mfe = cur;
      if(-cur > g_at[i].mae) g_at[i].mae = -cur;
     }
  }

void AnalyzerOnExit(ulong deal, double price, double net)
  {
   if(!InpAnalyzer)
      return;
   int i = AFind((ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID));
   if(i < 0)
      return;
   g_at[i].net   += net;
   g_at[i].pts    = (price - g_at[i].entry) * g_at[i].dir / _Point;
   g_at[i].durSec = (int)((datetime)HistoryDealGetInteger(deal, DEAL_TIME) - g_at[i].tOpen);
   g_at[i].reason = (int)HistoryDealGetInteger(deal, DEAL_REASON);
   g_at[i].closed = true;
  }

void AAdd(ABucket &b[], int idx, const ATrade &t)
  {
   if(idx < 0 || idx >= ArraySize(b))
      return;
   b[idx].n++;
   if(t.net > 0) b[idx].w++;
   if(t.net < 0 && t.reason == DEAL_REASON_SL) b[idx].sl++;
   b[idx].pts += t.pts;
   b[idx].usd += t.net;
  }

void APrint(string title, ABucket &b[], string &labels[])
  {
   Print("[ANALYZER] ---- ", title, " ----");
   Print("[ANALYZER]   bucket                 trades   win%   SL-loss   avgPts    netPts       net$");
   for(int i = 0; i < ArraySize(b); i++)
     {
      if(b[i].n == 0)
         continue;
      Print(StringFormat("[ANALYZER]   %-22s %6d  %5.1f  %8d  %7.1f  %8.0f  %10.2f",
                         labels[i], b[i].n, 100.0 * b[i].w / b[i].n, b[i].sl,
                         b[i].pts / b[i].n, b[i].pts, b[i].usd));
     }
  }

int ABin(double v, const double &edges[])
  {
   int n = ArraySize(edges);
   for(int i = 0; i < n; i++)
      if(v < edges[i])
         return i;
   return n;
  }

double OnTester()
  {
   if(!InpAnalyzer || g_atN == 0)
      return 0;

   ABucket bSrv[24], bPht[24], bDay[7], bDir[2], bTrend[3], bAtr[6], bRsi[5], bEma[5], bAdx[5], bSpr[4], bExit[4];
   ABucket bLossType[4], bLossTime[5];
   ZeroMemory(bSrv); ZeroMemory(bPht); ZeroMemory(bDay); ZeroMemory(bDir); ZeroMemory(bTrend);
   ZeroMemory(bAtr); ZeroMemory(bRsi); ZeroMemory(bEma); ZeroMemory(bAdx); ZeroMemory(bSpr);
   ZeroMemory(bExit); ZeroMemory(bLossType); ZeroMemory(bLossTime);

   double eAtr[] = {1, 2, 3, 5, 8};
   double eRsi[] = {30, 45, 55, 70};
   double eEma[] = {0.5, 1, 2, 3};
   double eAdx[] = {15, 20, 25, 35};
   double eSpr[] = {20, 35, 50};
   double eLossTime[] = {60, 300, 900, 3600};
   double trailStart = InpAtrStops ? 0 : g_trailStart;

   int total = 0, wins = 0, losses = 0, slippedLoss = 0, winsNearSL = 0;
   double grossW = 0, grossL = 0;
   for(int k = 0; k < g_atN; k++)
     {
      ATrade t = g_at[k];
      if(!t.closed)
         continue;
      total++;
      if(t.net > 0) { wins++; grossW += t.net; }
      else          { losses++; grossL += t.net; }

      AAdd(bSrv, t.srvHour, t);
      AAdd(bPht, t.phtHour, t);
      AAdd(bDay, t.wday, t);
      AAdd(bDir, t.dir > 0 ? 0 : 1, t);
      AAdd(bTrend, t.trend * t.dir > 0 ? 0 : (t.trend == 0 ? 1 : 2), t);
      AAdd(bAtr, ABin(t.atrUsd, eAtr), t);
      AAdd(bRsi, ABin(t.dir > 0 ? t.rsi : 100.0 - t.rsi, eRsi), t);
      AAdd(bEma, ABin(t.emaDistAtr, eEma), t);
      AAdd(bAdx, ABin(t.adx, eAdx), t);
      AAdd(bSpr, ABin(t.spread, eSpr), t);
      int ex = t.reason == DEAL_REASON_SL ? 0 : t.reason == DEAL_REASON_TP ? 1 : t.reason == DEAL_REASON_EXPERT ? 2 : 3;
      AAdd(bExit, ex, t);

      if(t.net > 0 && t.slPts > 0 && t.mae >= 0.7 * t.slPts)
         winsNearSL++;
      if(t.net < 0)
        {
         int lt;
         if(t.mfe < 30)                                 lt = 0;
         else if(t.mfe < 100)                           lt = 1;
         else if(trailStart <= 0 || t.mfe < trailStart) lt = 2;
         else                                           lt = 3;
         AAdd(bLossType, lt, t);
         AAdd(bLossTime, ABin(t.durSec, eLossTime), t);
         if(t.slPts > 0 && -t.pts > t.slPts + 20)
            slippedLoss++;
        }
     }
   if(total == 0)
      return 0;

   string lHour[24];
   for(int h = 0; h < 24; h++)
      lHour[h] = StringFormat("%02d:00", h);
   string lDay[]   = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
   string lDir[]   = {"BUY", "SELL"};
   string lTrend[] = {"WITH trend", "NEUTRAL", "AGAINST trend"};
   string lAtr[]   = {"ATR < $1", "ATR $1-2", "ATR $2-3", "ATR $3-5", "ATR $5-8", "ATR >= $8"};
   string lRsi[]   = {"< 30 (counter)", "30-45", "45-55", "55-70", ">= 70 (chasing)"};
   string lEma[]   = {"< 0.5 ATR", "0.5-1 ATR", "1-2 ATR", "2-3 ATR", ">= 3 ATR (extended)"};
   string lAdx[]   = {"ADX < 15", "ADX 15-20", "ADX 20-25", "ADX 25-35", "ADX >= 35"};
   string lSpr[]   = {"< 20 pts", "20-35 pts", "35-50 pts", ">= 50 pts"};
   string lExit[]  = {"Stop loss/trail", "Take profit", "EA close", "Other"};
   string lLossType[] = {"INSTANT  MFE<$0.30", "SMALL    MFE $0.30-1", "NEAR TRAIL then rev", "PAST TRAIL (gap)"};
   string lLossTime[] = {"< 1 min", "1-5 min", "5-15 min", "15-60 min", "> 60 min"};

   Print("[ANALYZER] ================= JM THUNDER LOSS ANALYZER =================");
   Print(StringFormat("[ANALYZER] Trades %d | Wins %d (%.1f%%) | Losses %d | Gross win $%.2f | Gross loss $%.2f",
                      total, wins, 100.0 * wins / total, losses, grossW, grossL));
   Print(StringFormat("[ANALYZER] SL=%d pts  TP=%d pts  TrailStart=%.0f pts | Losses slipped past SL >$0.20: %d | Winners that dipped >=70%% of SL: %d",
                      g_slPts, g_tpPts, trailStart, slippedLoss, winsNearSL));

   APrint("LOSS TYPE (MFE = best profit before the loss)", bLossType, lLossType);
   APrint("TIME TO LOSS", bLossTime, lLossTime);
   APrint("BY HOUR (SERVER TIME)", bSrv, lHour);
   APrint("BY HOUR (PH TIME GMT+8)", bPht, lHour);
   APrint("BY WEEKDAY", bDay, lDay);
   APrint("BY DIRECTION", bDir, lDir);
   APrint("BY TREND AT ENTRY", bTrend, lTrend);
   APrint("BY ATR (VOLATILITY)", bAtr, lAtr);
   APrint("BY RSI (in trade direction)", bRsi, lRsi);
   APrint("BY DISTANCE FROM FAST EMA", bEma, lEma);
   APrint("BY ADX (TREND STRENGTH)", bAdx, lAdx);
   APrint("BY SPREAD AT ENTRY", bSpr, lSpr);
   APrint("BY EXIT REASON", bExit, lExit);
   Print("[ANALYZER] =================================================================");
   return 0;
  }
//+------------------------------------------------------------------+
