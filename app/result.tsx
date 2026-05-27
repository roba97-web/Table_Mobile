import * as FileSystem from 'expo-file-system/legacy';
import * as IntentLauncher from 'expo-intent-launcher';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

type ResultRow = Record<string, string | number>;

const rawApiUrl = process.env.EXPO_PUBLIC_API_URL?.trim() || 'http://127.0.0.1:8000';
const API_URL = /^http:\/\/[^/:]+$/i.test(rawApiUrl)
  ? `${rawApiUrl}:8000`
  : rawApiUrl.replace(/\/$/, '');

async function api<T>(path: string, body: object): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '요청 실패');
  return data as T;
}

export default function ResultScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ columns?: string; rows?: string }>();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const { columns, rows } = useMemo(() => {
    try {
      return {
        columns: JSON.parse(params.columns ?? '[]') as string[],
        rows: JSON.parse(params.rows ?? '[]') as ResultRow[],
      };
    } catch {
      return { columns: [], rows: [] };
    }
  }, [params.columns, params.rows]);

  async function createPdfFile(directory: string | null) {
    if (!directory) throw new Error('저장 폴더를 찾을 수 없습니다.');
    const data = await api<{ file_name: string; pdf_base64: string }>('/api/result-pdf', {
      columns,
      rows,
    });
    const uri = `${directory}${data.file_name}`;
    await FileSystem.writeAsStringAsync(uri, data.pdf_base64, {
      encoding: FileSystem.EncodingType.Base64,
    });
    return { ...data, uri };
  }

  async function openResultPdf() {
    if (Platform.OS !== 'android') {
      setMessage('PDF 바로 보기는 현재 Android에서만 지원합니다.');
      return;
    }

    setLoading(true);
    setMessage('PDF 여는 중...');
    try {
      const { uri } = await createPdfFile(FileSystem.cacheDirectory);
      const contentUri = await FileSystem.getContentUriAsync(uri);
      await IntentLauncher.startActivityAsync('android.intent.action.VIEW', {
        data: contentUri,
        type: 'application/pdf',
        flags: 1,
      });
      setMessage('PDF 보기창 열림');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'PDF 열기 실패');
    } finally {
      setLoading(false);
    }
  }

  async function saveResultPdf() {
    setLoading(true);
    setMessage('저장창 여는 중...');
    try {
      const data = await api<{ file_name: string; pdf_base64: string }>('/api/result-pdf', {
        columns,
        rows,
      });
      const result = await IntentLauncher.startActivityAsync('android.intent.action.CREATE_DOCUMENT', {
        type: 'application/pdf',
        extra: {
          'android.intent.extra.TITLE': data.file_name,
        },
      });
      if (result.resultCode !== IntentLauncher.ResultCode.Success || !result.data) {
        setMessage('저장이 취소되었습니다.');
        return;
      }
      await FileSystem.writeAsStringAsync(result.data, data.pdf_base64, {
        encoding: FileSystem.EncodingType.Base64,
      });
      const file_name = data.file_name;
      setMessage(`저장 완료: ${file_name}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '저장 실패');
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>통합 정원표 분석결과</Text>

      <Pressable style={styles.button} onPress={openResultPdf} disabled={loading || !rows.length}>
        <Text style={styles.buttonText}>PDF 바로 보기</Text>
      </Pressable>

      <Pressable style={styles.saveButton} onPress={saveResultPdf} disabled={loading || !rows.length}>
        <Text style={styles.saveText}>스마트폰에 저장</Text>
      </Pressable>

      <Pressable style={styles.backButton} onPress={() => router.back()}>
        <Text style={styles.backText}>닫기</Text>
      </Pressable>

      {loading ? <ActivityIndicator size="large" color="#0066cc" /> : null}
      {message ? <Text style={styles.message}>{message}</Text> : null}

      <ScrollView horizontal style={styles.tableWrap}>
        <View>
          <View style={styles.row}>
            {columns.map((col) => (
              <Text key={col} style={[styles.cell, columnStyle(col), styles.headCell]}>
                {col}
              </Text>
            ))}
          </View>
          {rows.map((row, index) => (
            <View key={index} style={styles.row}>
              {columns.map((col) => (
                <View key={col} style={[styles.cell, columnStyle(col)]}>
                  {col === '구분' ? (
                    <Text style={styles.cellText}>{String(row[col] ?? '')}</Text>
                  ) : (
                    <>
                      <Text style={styles.cellText}>{formatNumber(row[col])}</Text>
                      {showShare(col) ? (
                        <Text style={styles.shareText}>({formatShare(row[col], row['총정원'])})</Text>
                      ) : null}
                    </>
                  )}
                </View>
              ))}
            </View>
          ))}
        </View>
      </ScrollView>
    </ScrollView>
  );
}

function columnStyle(col: string) {
  return col === '구분' ? styles.labelCell : styles.numberCell;
}

function showShare(col: string) {
  return col !== '구분' && col !== '총정원';
}

function toNumber(value: string | number | undefined) {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function formatNumber(value: string | number | undefined) {
  const n = toNumber(value);
  if (n === 0) return '0';
  return n.toLocaleString('ko-KR');
}

function formatShare(value: string | number | undefined, totalValue: string | number | undefined) {
  const total = toNumber(totalValue);
  if (!total) return '0.0';
  return ((toNumber(value) / total) * 100).toFixed(1);
}

const styles = StyleSheet.create({
  container: {
    padding: 20,
    gap: 12,
    backgroundColor: '#fff',
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    marginTop: 20,
  },
  button: {
    backgroundColor: '#0066cc',
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  saveButton: {
    backgroundColor: '#1b7f3a',
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
  },
  saveText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  backButton: {
    borderWidth: 1,
    borderColor: '#0066cc',
    borderRadius: 10,
    padding: 12,
    alignItems: 'center',
  },
  backText: {
    color: '#0066cc',
    fontSize: 15,
    fontWeight: '700',
  },
  message: {
    color: '#333',
  },
  tableWrap: {
    marginTop: 8,
  },
  row: {
    flexDirection: 'row',
  },
  cell: {
    borderWidth: 1,
    borderColor: '#ddd',
    padding: 8,
    minHeight: 46,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cellText: {
    textAlign: 'center',
  },
  shareText: {
    marginTop: 2,
    fontSize: 11,
    color: '#666',
    textAlign: 'center',
  },
  labelCell: {
    width: 180,
  },
  numberCell: {
    width: 76,
  },
  headCell: {
    fontWeight: '700',
    backgroundColor: '#f2f4f6',
  },
});
