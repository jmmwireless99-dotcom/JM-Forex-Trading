import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { StatusBar as ExpoStatusBar } from 'expo-status-bar'
import * as Linking from 'expo-linking'
import { api, defaultApiBase, getApiBase, setApiBase } from './src/api'

const STRATEGIES = ['manual_only', 'EMA_RSI_Scalp', 'Liquidity_Sweep_SMC']

function money(n) {
  return Number(n || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function Chip({ label, tone = 'neutral' }) {
  return (
    <View style={[styles.chip, tone === 'good' && styles.chipGood, tone === 'bad' && styles.chipBad]}>
      <Text style={styles.chipText}>{label}</Text>
    </View>
  )
}

function Btn({ title, onPress, variant = 'primary', disabled }) {
  return (
    <Pressable
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.btn,
        variant === 'ghost' && styles.btnGhost,
        variant === 'danger' && styles.btnDanger,
        (disabled || pressed) && { opacity: disabled ? 0.45 : 0.85 },
      ]}
    >
      <Text
        style={[
          styles.btnText,
          variant === 'ghost' && styles.btnTextGhost,
          variant === 'danger' && styles.btnTextDanger,
        ]}
      >
        {title}
      </Text>
    </Pressable>
  )
}

export default function App() {
  const [busy, setBusy] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [apiBase, setApiBaseState] = useState(defaultApiBase())
  const [status, setStatus] = useState(null)
  const [account, setAccount] = useState(null)
  const [desk, setDesk] = useState(null)
  const [auto, setAuto] = useState(null)
  const [trades, setTrades] = useState([])
  const [summary, setSummary] = useState(null)
  const [gold, setGold] = useState(null)
  const [strategy, setStrategy] = useState('manual_only')
  const [strategies, setStrategies] = useState(STRATEGIES)

  const load = useCallback(async () => {
    setError('')
    try {
      const base = await getApiBase()
      setApiBaseState(base)
      const [st, acc, d, a, tr, tk, strat] = await Promise.all([
        api.status(),
        api.account(),
        api.desk(),
        api.auto(),
        api.trades(30),
        api.ticks(),
        api.strategies(),
      ])
      setStatus(st)
      setAccount(acc)
      setDesk(d)
      setAuto(a)
      setTrades(tr.trades || [])
      setSummary(tr.summary || null)
      setStrategies(strat.strategies?.length ? strat.strategies : STRATEGIES)
      const xau = (tk.ticks || []).find((t) => t.symbol === 'XAUUSD')
      setGold(xau || null)
      const label = st.active_strategy || ''
      if (label.startsWith('auto_gold') || label === 'auto') setStrategy('manual_only')
      else if (label) setStrategy(label)
    } catch (err) {
      setError(err.message || 'Failed to reach desk API')
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 8000)
    return () => clearInterval(id)
  }, [load])

  async function run(action) {
    setBusy(true)
    setError('')
    try {
      await action()
      await load()
    } catch (err) {
      setError(err.message || 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  const rec = desk?.recommended_now || auto?.recommended
  const running = Boolean(status?.running)
  const pnl = Number(account?.daily_pnl || 0)

  const strategyButtons = useMemo(
    () =>
      strategies.map((name) => (
        <Pressable
          key={name}
          onPress={() => setStrategy(name)}
          style={[styles.stratPill, strategy === name && styles.stratPillOn]}
        >
          <Text style={[styles.stratPillText, strategy === name && styles.stratPillTextOn]}>
            {name === 'manual_only' ? 'manual_only (clean slate)' : name}
          </Text>
        </Pressable>
      )),
    [strategies, strategy],
  )

  return (
    <SafeAreaView style={styles.safe}>
      <ExpoStatusBar style="light" />
      <StatusBar barStyle="light-content" />
      <ScrollView
        contentContainerStyle={styles.container}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            tintColor="#F2C14E"
            onRefresh={async () => {
              setRefreshing(true)
              await load()
              setRefreshing(false)
            }}
          />
        }
      >
        <Text style={styles.brand}>
          JM <Text style={styles.brandAccent}>Forex</Text>
        </Text>
        <Text style={styles.tagline}>XAUUSD desk · Android</Text>

        <View style={styles.row}>
          <Chip label={running ? 'Desk live' : 'Paused'} tone={running ? 'good' : 'neutral'} />
          <Chip label={(status?.mode || 'paper').toUpperCase()} />
          <Chip
            label={auto?.enabled ? 'AUTO ON' : 'MANUAL'}
            tone={auto?.enabled ? 'good' : 'neutral'}
          />
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <View style={styles.card}>
          <Text style={styles.label}>XAUUSD</Text>
          <Text style={styles.price}>{gold ? gold.mid : '—'}</Text>
          <Text style={styles.meta}>
            Strategy: {status?.active_strategy || '—'}
          </Text>
          <Text style={styles.meta}>
            {rec?.session || desk?.session?.label || '—'} · {rec?.regime || auto?.decision?.regime || '—'}
          </Text>
        </View>

        <View style={styles.metrics}>
          <View style={styles.metric}>
            <Text style={styles.label}>Equity</Text>
            <Text style={styles.metricVal}>${money(account?.equity)}</Text>
          </View>
          <View style={styles.metric}>
            <Text style={styles.label}>Daily P&L</Text>
            <Text style={[styles.metricVal, pnl >= 0 ? styles.gain : styles.loss]}>
              ${money(pnl)}
            </Text>
          </View>
          <View style={styles.metric}>
            <Text style={styles.label}>Open</Text>
            <Text style={styles.metricVal}>{account?.open_positions ?? 0}</Text>
          </View>
          <View style={styles.metric}>
            <Text style={styles.label}>Win%</Text>
            <Text style={styles.metricVal}>{summary?.win_rate_pct ?? '—'}%</Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.section}>Scalp strategies</Text>
          <Text style={styles.recommend}>
            {status?.active_strategy || 'manual_only'}
          </Text>
          <Text style={styles.meta}>
            {rec?.reason || 'EMA_RSI_Scalp · Liquidity_Sweep_SMC · manual'}
          </Text>
          <View style={styles.actions}>
            <Text style={styles.meta}>
              Active now:{' '}
              {(rec?.session || desk?.session?.label || '—').replace(/_/g, ' ')} session
            </Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.section}>Strategy</Text>
          <View style={styles.stratWrap}>{strategyButtons}</View>
          <View style={styles.actions}>
            <Btn
              title="Apply strategy"
              variant="ghost"
              disabled={busy}
              onPress={() => run(() => api.setStrategy(strategy))}
            />
            <Btn
              title={running ? 'Restart / keep live' : 'Start engine'}
              disabled={busy}
              onPress={() =>
                run(async () => {
                  await api.setStrategy(strategy)
                  await api.start(strategy)
                })
              }
            />
            <Btn
              title="Stop"
              variant="danger"
              disabled={busy || !running}
              onPress={() => run(() => api.stop())}
            />
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.section}>Recent trades</Text>
          {trades.length === 0 ? (
            <Text style={styles.meta}>No trades yet</Text>
          ) : (
            trades.slice(0, 8).map((t) => (
              <View key={t.id || t.ticket} style={styles.tradeRow}>
                <Text style={styles.tradeSide}>{t.side}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.tradeMain}>
                    {t.strategy} · {t.close_reason || t.status}
                  </Text>
                  <Text style={styles.meta}>
                    {t.entry} → {t.exit ?? 'open'} · SL {t.stop_loss ?? '—'} TP {t.take_profit ?? '—'}
                  </Text>
                </View>
                <Text
                  style={[
                    styles.tradePnl,
                    Number(t.realized_pnl) >= 0 ? styles.gain : styles.loss,
                  ]}
                >
                  {money(t.realized_pnl)}
                </Text>
              </View>
            ))
          )}
        </View>

        <View style={styles.card}>
          <Text style={styles.section}>API server</Text>
          <TextInput
            style={styles.input}
            value={apiBase}
            autoCapitalize="none"
            autoCorrect={false}
            onChangeText={setApiBaseState}
            placeholder="https://jmtechsolution.cloud/fx/api"
            placeholderTextColor="#6f8a84"
          />
          <View style={styles.actions}>
            <Btn
              title="Save API"
              variant="ghost"
              disabled={busy}
              onPress={() =>
                run(async () => {
                  await setApiBase(apiBase)
                })
              }
            />
            <Btn
              title="Open web desk"
              variant="ghost"
              onPress={() => Linking.openURL('https://jmtechsolution.cloud/fx/')}
            />
          </View>
          {busy ? <ActivityIndicator color="#F2C14E" style={{ marginTop: 10 }} /> : null}
        </View>

        <Text style={styles.footer}>
          JM TECH SOLUTION · pull to refresh · controls talk to the live paper/MT desk
        </Text>
      </ScrollView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#071412' },
  container: { padding: 18, paddingBottom: 40, gap: 12 },
  brand: {
    fontSize: 40,
    color: '#F4F7F6',
    fontWeight: '700',
    letterSpacing: -0.5,
  },
  brandAccent: { color: '#F2C14E' },
  tagline: { color: '#8aa39c', marginTop: -4, marginBottom: 4 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderColor: 'rgba(255,255,255,0.1)',
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
  },
  chipGood: { borderColor: 'rgba(125,255,179,0.45)', backgroundColor: 'rgba(125,255,179,0.12)' },
  chipBad: { borderColor: 'rgba(255,107,107,0.45)', backgroundColor: 'rgba(255,107,107,0.12)' },
  chipText: { color: '#E7EFEC', fontSize: 12, fontWeight: '600' },
  error: {
    color: '#ffb4b4',
    backgroundColor: 'rgba(255,107,107,0.12)',
    borderColor: 'rgba(255,107,107,0.3)',
    borderWidth: 1,
    padding: 10,
    borderRadius: 10,
  },
  card: {
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderColor: 'rgba(201,162,39,0.22)',
    borderWidth: 1,
    borderRadius: 16,
    padding: 14,
    gap: 6,
  },
  label: { color: '#8aa39c', fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6 },
  price: { color: '#F2C14E', fontSize: 34, fontWeight: '700' },
  meta: { color: '#8aa39c', fontSize: 13, lineHeight: 18 },
  section: { color: '#F2C14E', fontWeight: '700', marginBottom: 2 },
  recommend: { color: '#F4F7F6', fontSize: 20, fontWeight: '700' },
  metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  metric: {
    width: '47%',
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
  },
  metricVal: { color: '#F4F7F6', fontSize: 20, fontWeight: '700', marginTop: 2 },
  gain: { color: '#7DFFB3' },
  loss: { color: '#ff8f8f' },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  btn: {
    backgroundColor: '#C9A227',
    paddingHorizontal: 14,
    paddingVertical: 11,
    borderRadius: 12,
  },
  btnGhost: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: 'rgba(201,162,39,0.45)',
  },
  btnDanger: { backgroundColor: '#8b2e2e' },
  btnText: { color: '#071412', fontWeight: '700', fontSize: 13 },
  btnTextGhost: { color: '#F2C14E' },
  btnTextDanger: { color: '#fff5f5' },
  stratWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  stratPill: {
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  stratPillOn: {
    borderColor: '#F2C14E',
    backgroundColor: 'rgba(242,193,78,0.15)',
  },
  stratPillText: { color: '#9fb4ae', fontSize: 12 },
  stratPillTextOn: { color: '#F2C14E', fontWeight: '700' },
  tradeRow: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'flex-start',
    paddingVertical: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(255,255,255,0.08)',
  },
  tradeSide: { color: '#F2C14E', fontWeight: '700', width: 36, marginTop: 2 },
  tradeMain: { color: '#E7EFEC', fontSize: 13, fontWeight: '600' },
  tradePnl: { fontWeight: '700', fontSize: 13 },
  input: {
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.14)',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: '#F4F7F6',
    marginTop: 4,
  },
  footer: { color: '#5f7771', fontSize: 11, textAlign: 'center', marginTop: 8 },
})
