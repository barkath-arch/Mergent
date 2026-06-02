import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, spacing, radius, font } from '../theme';

/* ---------- SolutionCard ---------- */
export function SolutionCard({ s }: { s: any }) {
  const router = useRouter();
  return (
    <TouchableOpacity
      testID={`solution-card-${s.id}`}
      style={styles.card}
      activeOpacity={0.7}
      onPress={() => router.push(`/solutions/${s.id}` as any)}
    >
      <View style={styles.row}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text testID={`solution-title-${s.id}`} style={styles.cardTitle} numberOfLines={1}>{s.title}</Text>
          <Text style={styles.dim}>{s.builder_name}</Text>
        </View>
        <View style={styles.chipMuted}><Text style={styles.chipMutedText}>{s.category}</Text></View>
      </View>
      <Text style={styles.bodyMuted} numberOfLines={2}>{s.tagline}</Text>
      <View style={[styles.rowBetween, { marginTop: 8 }]}>
        <View style={styles.row}>
          <View style={styles.chipEmerald}>
            <Text testID={`solution-price-${s.id}`} style={styles.chipEmeraldText}>${s.price_usd?.toLocaleString?.() ?? s.price_usd}</Text>
          </View>
          {s.builder_rating ? (
            <View style={[styles.chip, { marginLeft: 6 }]}>
              <Text style={styles.chipText}>★ {s.builder_rating?.toFixed?.(1) ?? s.builder_rating}</Text>
            </View>
          ) : null}
        </View>
        <Text style={styles.dimMono}>{s.clients_count || 0} clients</Text>
      </View>
    </TouchableOpacity>
  );
}

/* ---------- RequirementRow ---------- */
export function RequirementRow({ r }: { r: any }) {
  return (
    <View testID={`requirement-row-${r.id}`} style={[styles.card, { padding: 14 }]}>
      <View style={styles.rowBetween}>
        <Text style={styles.cardTitle} numberOfLines={1}>{r.title}</Text>
        {r.budget_usd ? (
          <View style={styles.chipEmerald}><Text style={styles.chipEmeraldText}>${r.budget_usd.toLocaleString()}</Text></View>
        ) : (
          <View style={styles.chipMuted}><Text style={styles.chipMutedText}>No budget</Text></View>
        )}
      </View>
      <Text style={[styles.bodyMuted, { marginTop: 4 }]} numberOfLines={2}>{r.summary}</Text>
      <View style={[styles.rowBetween, { marginTop: 8 }]}>
        <View style={styles.chipMuted}><Text style={styles.chipMutedText}>{r.category}</Text></View>
        <Text style={styles.dimMono}>{r.match_count || 0} matches</Text>
      </View>
    </View>
  );
}

/* ---------- Stat ---------- */
export function Stat({ label, value, delta }: { label: string; value: any; delta?: string }) {
  return (
    <View testID={`stat-${label.toLowerCase().replace(/\s+/g, '-')}`} style={styles.card}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
      {delta ? <Text style={styles.statDelta}>{delta}</Text> : null}
    </View>
  );
}

/* ---------- Empty ---------- */
export function Empty({ title = 'Nothing here yet', hint }: { title?: string; hint?: string }) {
  return (
    <View testID="empty-state" style={[styles.card, { alignItems: 'center', padding: 56 }]}>
      <Text style={{ fontSize: 16, fontWeight: '500', color: colors.text }}>{title}</Text>
      {hint ? <Text style={[styles.bodyMuted, { marginTop: 8 }]}>{hint}</Text> : null}
    </View>
  );
}

/* ---------- PageHeader ---------- */
export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <View testID="page-header" style={[styles.rowBetween, { marginBottom: 24 }]}>
      <View style={{ flex: 1 }}>
        <Text style={styles.h1}>{title}</Text>
        {subtitle ? <Text style={[styles.bodyMuted, { marginTop: 6 }]}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  );
}

/* ---------- Loader ---------- */
export function Loader() {
  return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.bg0 }}>
      <ActivityIndicator size="large" color={colors.violet} />
    </View>
  );
}

/* ---------- Chip ---------- */
export function Chip({ text, variant = 'default' }: { text: string; variant?: 'default' | 'emerald' | 'amber' | 'rose' | 'muted' }) {
  const chipStyle = variant === 'emerald' ? styles.chipEmerald
    : variant === 'amber' ? styles.chipAmber
    : variant === 'rose' ? styles.chipRose
    : variant === 'muted' ? styles.chipMuted
    : styles.chip;
  const textStyle = variant === 'emerald' ? styles.chipEmeraldText
    : variant === 'amber' ? styles.chipAmberText
    : variant === 'rose' ? styles.chipRoseText
    : variant === 'muted' ? styles.chipMutedText
    : styles.chipText;
  return <View style={chipStyle}><Text style={textStyle}>{text}</Text></View>;
}

/* ---------- Btn ---------- */
export function Btn({ title, onPress, disabled, loading: isLoading, variant = 'primary', testID, style: extraStyle }: {
  title: string; onPress?: () => void; disabled?: boolean; loading?: boolean;
  variant?: 'primary' | 'secondary' | 'ghost'; testID?: string; style?: any;
}) {
  const btnStyle = variant === 'secondary' ? styles.btnSecondary : variant === 'ghost' ? styles.btnGhost : styles.btn;
  const txtStyle = variant === 'secondary' ? styles.btnSecondaryText : variant === 'ghost' ? styles.btnGhostText : styles.btnText;
  return (
    <TouchableOpacity
      testID={testID}
      onPress={onPress}
      disabled={disabled || isLoading}
      activeOpacity={0.7}
      style={[btnStyle, (disabled || isLoading) && { opacity: 0.5 }, extraStyle]}
    >
      {isLoading ? <ActivityIndicator size="small" color={colors.white} /> : <Text style={txtStyle}>{title}</Text>}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: 18,
    marginBottom: 12,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  h1: { fontSize: font.xxl, fontWeight: '600', color: colors.text, letterSpacing: -0.5 },
  cardTitle: { fontSize: font.lg, fontWeight: '600', color: colors.text },
  dim: { fontSize: font.sm, color: colors.textDim },
  dimMono: { fontSize: 11, color: colors.textDim, fontFamily: 'monospace' },
  bodyMuted: { fontSize: font.base, color: colors.textMuted, lineHeight: 20 },
  statLabel: { fontSize: 11, textTransform: 'uppercase', letterSpacing: 1, color: colors.textDim },
  statValue: { fontSize: 26, fontWeight: '600', color: colors.text, marginTop: 4 },
  statDelta: { fontSize: 11.5, color: colors.emerald, marginTop: 2 },
  chip: { backgroundColor: 'rgba(139,92,246,0.12)', borderWidth: 1, borderColor: 'rgba(139,92,246,0.28)', borderRadius: radius.full, paddingHorizontal: 10, paddingVertical: 3 },
  chipText: { fontSize: 11.5, fontWeight: '500', color: colors.violet2 },
  chipMuted: { backgroundColor: 'rgba(255,255,255,0.04)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.full, paddingHorizontal: 10, paddingVertical: 3 },
  chipMutedText: { fontSize: 11.5, fontWeight: '500', color: colors.textMuted },
  chipEmerald: { backgroundColor: 'rgba(74,222,128,0.1)', borderWidth: 1, borderColor: 'rgba(74,222,128,0.3)', borderRadius: radius.full, paddingHorizontal: 10, paddingVertical: 3 },
  chipEmeraldText: { fontSize: 11.5, fontWeight: '500', color: colors.emerald },
  chipAmber: { backgroundColor: 'rgba(251,191,36,0.1)', borderWidth: 1, borderColor: 'rgba(251,191,36,0.3)', borderRadius: radius.full, paddingHorizontal: 10, paddingVertical: 3 },
  chipAmberText: { fontSize: 11.5, fontWeight: '500', color: colors.amber },
  chipRose: { backgroundColor: 'rgba(251,113,133,0.1)', borderWidth: 1, borderColor: 'rgba(251,113,133,0.3)', borderRadius: radius.full, paddingHorizontal: 10, paddingVertical: 3 },
  chipRoseText: { fontSize: 11.5, fontWeight: '500', color: colors.rose },
  btn: {
    backgroundColor: colors.violet,
    borderRadius: radius.md,
    paddingVertical: 12,
    paddingHorizontal: 20,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  btnText: { color: colors.white, fontWeight: '500', fontSize: font.md },
  btnSecondary: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    paddingVertical: 12,
    paddingHorizontal: 20,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  btnSecondaryText: { color: colors.text, fontWeight: '500', fontSize: font.md },
  btnGhost: {
    backgroundColor: 'transparent',
    borderRadius: radius.md,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnGhostText: { color: colors.textMuted, fontSize: font.md },
});
