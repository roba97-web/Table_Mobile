import { Picker } from '@react-native-picker/picker';
import { router, type Href } from 'expo-router';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

type StaffItem = {
  form_title: string;
  file_name: string;
  pdf_base64: string;
};

type QuotaMode = '기준정원' | '운영정원';
type ResultRow = Record<string, string | number>;

type FrameGroup = {
  label: string;
  indices: number[];
  isTemporaryFrame: boolean;
};

const rawApiUrl = process.env.EXPO_PUBLIC_API_URL?.trim() || 'http://127.0.0.1:8000';
const API_URL = /^https?:\/\/[^/:]+$/i.test(rawApiUrl)
  ? `${rawApiUrl}:8000`
  : rawApiUrl.replace(/\/$/, '');

async function api<T>(path: string, body?: object): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '요청 실패');
  return data as T;
}

function compact(text: string) {
  return text.replace(/\s+/g, '').trim();
}

function itemText(item: StaffItem) {
  return `${item.form_title} ${item.file_name}`;
}

function sourceTitle(item: StaffItem) {
  return item.form_title.trim() || item.file_name.replace(/\.pdf$/i, '').trim();
}

function titlePrefix(item: StaffItem) {
  const source = sourceTitle(item);
  const beforeQuota = source.includes('정원표') ? source.split('정원표')[0] : source;
  const withoutStaff = beforeQuota.trim().replace(/공무원$/, '').trim();
  if (withoutStaff.includes('사무처') && !withoutStaff.includes(' 사무처')) {
    const pos = withoutStaff.indexOf('사무처');
    if (pos > 0) return `${withoutStaff.slice(0, pos).trim()} ${withoutStaff.slice(pos).trim()}`;
  }
  return withoutStaff || '본부';
}

function isTemporaryFrameItem(item: StaffItem, selectedOrg: string) {
  const text = itemText(item);
  return text.includes('한시') && compact(text).includes(compact(selectedOrg));
}

function frameLabel(item: StaffItem, selectedOrg: string) {
  if (isTemporaryFrameItem(item, selectedOrg)) return '한시조직 및 정원';

  const prefix = titlePrefix(item);
  if (!prefix || compact(prefix) === compact(selectedOrg)) return '본부';
  return prefix;
}

function analyzeLabel(item: StaffItem, group: FrameGroup) {
  if (!group.isTemporaryFrame) return group.label;
  return itemText(item).includes('한시조직에 두는') ? '한시조직' : '한시정원';
}

function buildFrameGroups(items: StaffItem[], selectedOrg: string): FrameGroup[] {
  const order: string[] = [];
  const buckets = new Map<string, number[]>();

  items.forEach((item, index) => {
    const label = frameLabel(item, selectedOrg);
    if (!buckets.has(label)) {
      buckets.set(label, []);
      order.push(label);
    }
    buckets.get(label)!.push(index);
  });

  return order.map((label) => {
    const indices = buckets.get(label)!;
    return {
      label,
      indices,
      isTemporaryFrame: indices.some((index) => isTemporaryFrameItem(items[index], selectedOrg)),
    };
  });
}

function selectedIndexForGroup(group: FrameGroup, quotaMode: QuotaMode) {
  if (group.indices.length === 1) return group.indices[0];
  if (group.indices.length === 2) return quotaMode === '기준정원' ? group.indices[0] : group.indices[1];
  return group.indices[0];
}

export default function HomeScreen() {
  const [serverOk, setServerOk] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [orgs, setOrgs] = useState<string[]>([]);
  const [selectedOrg, setSelectedOrg] = useState('');
  const [items, setItems] = useState<StaffItem[]>([]);
  const [quotaMode, setQuotaMode] = useState<QuotaMode>('기준정원');
  const [includeTemporary, setIncludeTemporary] = useState(false);
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<ResultRow[]>([]);

  useEffect(() => {
    api<{ status: string }>('/health')
      .then(() => setServerOk(true))
      .catch(() => setServerOk(false));
  }, []);

  const statusText = useMemo(
    () => (serverOk ? `서버 연결됨: ${API_URL}` : `서버 연결 안됨: ${API_URL}`),
    [serverOk],
  );

  const frameGroups = useMemo(
    () => (selectedOrg ? buildFrameGroups(items, selectedOrg) : []),
    [items, selectedOrg],
  );

  const analysisItems = useMemo(
    () =>
      frameGroups
        .filter((group) => includeTemporary || !group.isTemporaryFrame)
        .map((group) => {
          const index = selectedIndexForGroup(group, quotaMode);
          return {
            item: items[index],
            label: analyzeLabel(items[index], group),
          };
        }),
    [frameGroups, includeTemporary, items, quotaMode],
  );

  async function loadLaw() {
    setLoading(true);
    setMessage('');
    try {
      const data = await api<{ org_options: string[] }>('/api/step1/load-law', {});
      setOrgs(data.org_options);
      setItems([]);
      setRows([]);
      setMessage(`정부조직법 불러오기 완료 (${data.org_options.length}개)`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '불러오기 실패');
    } finally {
      setLoading(false);
    }
  }

  async function fetchStaff() {
    if (!selectedOrg) {
      setMessage('기관을 먼저 선택하세요.');
      return;
    }
    setLoading(true);
    setMessage('');
    try {
      const data = await api<{ items: StaffItem[] }>('/api/step2/fetch-staff', {
        org_name: selectedOrg,
      });
      setItems(data.items);
      setRows([]);
      setMessage(`정원표 PDF ${data.items.length}건 조회 완료`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '정원표 조회 실패');
    } finally {
      setLoading(false);
    }
  }

  async function analyze() {
    if (!analysisItems.length) {
      setMessage('조회된 정원표가 없습니다.');
      return;
    }
    setLoading(true);
    setMessage('');
    try {
      const data = await api<{ columns: string[]; rows: ResultRow[] }>('/api/analyze', {
        selections: analysisItems.map(({ item, label }) => ({
          pdf_base64: item.pdf_base64,
          label,
        })),
      });
      setColumns(data.columns);
      setRows(data.rows);
      setMessage('분석 완료');
      router.push({
        pathname: '/result',
        params: {
          columns: JSON.stringify(data.columns),
          rows: JSON.stringify(data.rows),
        },
      } as unknown as Href);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '분석 실패');
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <TextBlock style={styles.title}>부처 정원표 자동</TextBlock>
      <TextBlock style={[styles.status, serverOk ? styles.ok : styles.error]}>{statusText}</TextBlock>

      <Button title="정부조직법 불러오기" onPress={loadLaw} disabled={loading} />

      <View style={styles.pickerBox}>
        <Picker selectedValue={selectedOrg} onValueChange={(value) => setSelectedOrg(String(value))}>
          <Picker.Item label="기관 선택" value="" />
          {orgs.map((org) => (
            <Picker.Item key={org} label={org} value={org} />
          ))}
        </Picker>
      </View>

      <Button title="선택한 기관 정원표 조회" onPress={fetchStaff} disabled={loading || !orgs.length} />

      {items.length ? (
        <View style={styles.optionBox}>
          <TextBlock style={styles.optionTitle}>정원 기준</TextBlock>
          <View style={styles.optionRow}>
            <Chip title="기준정원" active={quotaMode === '기준정원'} onPress={() => setQuotaMode('기준정원')} />
            <Chip title="운영정원" active={quotaMode === '운영정원'} onPress={() => setQuotaMode('운영정원')} />
          </View>
          <Pressable
            style={styles.checkRow}
            onPress={() => setIncludeTemporary((current) => !current)}>
            <View style={[styles.checkbox, includeTemporary && styles.checkboxOn]} />
            <TextBlock style={styles.checkText}>한시조직 포함</TextBlock>
          </Pressable>
          <TextBlock style={styles.optionHint}>
            분석 대상 {analysisItems.length}건 / 프레임 {frameGroups.length}개 / 전체 PDF {items.length}건
          </TextBlock>
        </View>
      ) : null}

      <Button title="정원표 출력" onPress={analyze} disabled={loading || !items.length} />

      {loading ? <ActivityIndicator size="large" color="#0066cc" /> : null}
      {message ? <TextBlock style={styles.message}>{message}</TextBlock> : null}

      {frameGroups.map((group) => (
        <FrameCard
          key={group.label}
          group={group}
          items={items}
          quotaMode={quotaMode}
          includeTemporary={includeTemporary}
        />
      ))}

    </ScrollView>
  );
}

function Button({ title, onPress, disabled }: { title: string; onPress: () => void; disabled?: boolean }) {
  return (
    <Pressable style={[styles.button, disabled && styles.disabled]} onPress={onPress} disabled={disabled}>
      <TextBlock style={styles.buttonText}>{title}</TextBlock>
    </Pressable>
  );
}

function Chip({ title, active, onPress }: { title: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable style={[styles.chip, active && styles.chipActive]} onPress={onPress}>
      <TextBlock style={[styles.chipText, active && styles.chipTextActive]}>{title}</TextBlock>
    </Pressable>
  );
}

function FrameCard({
  group,
  items,
  quotaMode,
  includeTemporary,
}: {
  group: FrameGroup;
  items: StaffItem[];
  quotaMode: QuotaMode;
  includeTemporary: boolean;
}) {
  const selectedIndex = selectedIndexForGroup(group, quotaMode);
  const frameEnabled = !group.isTemporaryFrame || includeTemporary;

  return (
    <View style={[styles.frameCard, !frameEnabled && styles.frameCardOff]}>
      <View style={styles.frameHeader}>
        <TextBlock style={styles.frameTitle}>{group.label}</TextBlock>
        {group.isTemporaryFrame ? <TextBlock style={styles.tempBadge}>한시</TextBlock> : null}
      </View>

      {group.indices.map((itemIndex, rowIndex) => {
        const item = items[itemIndex];
        const rowLabel =
          group.indices.length === 2
            ? rowIndex === 0
              ? '기준정원'
              : '운영정원'
            : group.indices.length > 2
              ? '기관명'
              : '';
        const selected = frameEnabled && itemIndex === selectedIndex;

        return (
          <View key={`${item.file_name}-${itemIndex}`} style={[styles.frameRow, selected && styles.frameRowOn]}>
            {rowLabel ? <TextBlock style={styles.rowLabel}>{rowLabel}</TextBlock> : null}
            <View style={styles.framePdfText}>
              <TextBlock style={styles.cardTitle}>{item.form_title}</TextBlock>
              <TextBlock style={styles.cardSub}>{item.file_name}</TextBlock>
            </View>
            {selected ? <TextBlock style={styles.selectedMark}>선택</TextBlock> : null}
          </View>
        );
      })}
    </View>
  );
}

function TextBlock({ children, style }: { children: ReactNode; style?: object }) {
  return <View><Text style={style}>{children}</Text></View>;
}

const styles = StyleSheet.create({
  container: {
    padding: 20,
    gap: 12,
    backgroundColor: '#fff',
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    marginTop: 20,
  },
  status: {
    fontSize: 13,
  },
  ok: {
    color: '#2e7d32',
  },
  error: {
    color: '#d32f2f',
  },
  button: {
    backgroundColor: '#0066cc',
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
  },
  disabled: {
    opacity: 0.45,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  pickerBox: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 10,
    overflow: 'hidden',
  },
  message: {
    fontSize: 14,
    color: '#333',
  },
  optionBox: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 10,
    padding: 12,
    gap: 10,
  },
  optionTitle: {
    fontSize: 15,
    fontWeight: '700',
  },
  optionRow: {
    flexDirection: 'row',
    gap: 8,
  },
  chip: {
    borderWidth: 1,
    borderColor: '#0066cc',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  chipActive: {
    backgroundColor: '#0066cc',
  },
  chipText: {
    color: '#0066cc',
    fontWeight: '700',
  },
  chipTextActive: {
    color: '#fff',
  },
  checkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  checkbox: {
    width: 20,
    height: 20,
    borderRadius: 4,
    borderWidth: 2,
    borderColor: '#0066cc',
  },
  checkboxOn: {
    backgroundColor: '#0066cc',
  },
  checkText: {
    fontSize: 14,
  },
  optionHint: {
    fontSize: 12,
    color: '#666',
  },
  frameCard: {
    borderWidth: 1,
    borderColor: '#d0d7de',
    borderRadius: 12,
    padding: 12,
    gap: 8,
    backgroundColor: '#fafafa',
  },
  frameCardOff: {
    opacity: 0.45,
  },
  frameHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  frameTitle: {
    fontSize: 17,
    fontWeight: '700',
  },
  tempBadge: {
    color: '#d32f2f',
    fontSize: 12,
    fontWeight: '700',
  },
  frameRow: {
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 10,
    padding: 10,
    gap: 4,
    backgroundColor: '#fff',
  },
  frameRowOn: {
    borderColor: '#0066cc',
    backgroundColor: '#eef6ff',
  },
  rowLabel: {
    color: '#0066cc',
    fontSize: 13,
    fontWeight: '700',
  },
  framePdfText: {
    gap: 2,
  },
  selectedMark: {
    color: '#0066cc',
    fontSize: 12,
    fontWeight: '700',
  },
  card: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 10,
    padding: 12,
    gap: 4,
  },
  cardOff: {
    opacity: 0.45,
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: '700',
  },
  cardSub: {
    fontSize: 12,
    color: '#666',
  },
  selectButton: {
    marginTop: 8,
    borderWidth: 1,
    borderColor: '#0066cc',
    borderRadius: 8,
    padding: 10,
    alignItems: 'center',
  },
  selectButtonOn: {
    backgroundColor: '#0066cc',
  },
  selectButtonText: {
    color: '#0066cc',
    fontWeight: '700',
  },
  selectButtonTextOn: {
    color: '#fff',
  },
  tableWrap: {
    marginTop: 10,
  },
  row: {
    flexDirection: 'row',
  },
  cell: {
    minWidth: 80,
    borderWidth: 1,
    borderColor: '#ddd',
    padding: 8,
    textAlign: 'center',
  },
  headCell: {
    fontWeight: '700',
    backgroundColor: '#f2f4f6',
  },
});
