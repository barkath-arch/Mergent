import React, { useEffect, useRef, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView, FlatList, StyleSheet, KeyboardAvoidingView, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api, { WS_BASE, getAccessToken } from '../../src/api';
import { useAuth } from '../../src/auth';
import { PageHeader, Empty } from '../../src/components/UI';
import { colors, radius } from '../../src/theme';

export default function MessagesTab() {
  const { user } = useAuth();
  const [convs, setConvs] = useState<any[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [text, setText] = useState('');
  const [typing, setTyping] = useState<string | null>(null);
  const listRef = useRef<ScrollView>(null);

  const load = () => api.get('/conversations').then(r => setConvs(r.data.items)).catch(() => {});
  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!user) return;
    const url = `${WS_BASE}/conversations/${user.id}?token=${getAccessToken()}`;
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
      ws.onmessage = (e: any) => {
        try {
          const m = JSON.parse(e.data);
          if (m.type === 'new_message') { load(); if (m.conversation_id === activeId) setMessages(prev => [...prev, m.message]); }
          if (m.type === 'typing' && m.conversation_id === activeId) {
            setTyping(m.is_typing ? m.user_id : null);
            if (m.is_typing) setTimeout(() => setTyping(null), 2500);
          }
        } catch {}
      };
    } catch {}
    return () => { try { ws?.close(); } catch {} };
  }, [user, activeId]);

  useEffect(() => {
    if (!activeId) return;
    api.get(`/conversations/${activeId}/messages`).then(r => setMessages(r.data.items)).catch(() => {});
  }, [activeId]);

  useEffect(() => { listRef.current?.scrollToEnd?.({ animated: true }); }, [messages]);

  const send = async () => {
    if (!text.trim() || !activeId) return;
    const t = text.trim(); setText('');
    try {
      const r = await api.post(`/conversations/${activeId}/messages`, { text: t });
      setMessages(prev => [...prev, r.data]);
      load();
    } catch {}
  };

  const active = convs.find(c => c.id === activeId);
  const otherId = active?.participants?.find((p: string) => p !== user?.id);
  const otherName = active?.participant_names?.[otherId] || '—';

  // When no conversation selected, show list
  if (!activeId) {
    return (
      <SafeAreaView style={s.safe} edges={['top']}>
        <ScrollView style={s.scroll} contentContainerStyle={s.content}>
          <PageHeader title="Messages" subtitle="Coordinate with builders and buyers." />
          <View testID="messages-page">
            {convs.length === 0 ? (
              <Empty title="No conversations yet" />
            ) : (
              convs.map(c => {
                const otherUid = c.participants.find((p: string) => p !== user?.id);
                const otherN = c.participant_names?.[otherUid] || '—';
                return (
                  <TouchableOpacity key={c.id} testID={`conversation-item-${c.id}`} style={s.convItem} onPress={() => setActiveId(c.id)} activeOpacity={0.7}>
                    <View style={s.avatar}><Text style={s.avatarText}>{otherN[0]}</Text></View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.convName} numberOfLines={1}>{otherN}</Text>
                      <Text style={s.convLast} numberOfLines={1}>{c.last_message || '—'}</Text>
                    </View>
                    {c.unread_for_me ? <View style={s.badge}><Text style={s.badgeText}>{c.unread_for_me}</Text></View> : null}
                  </TouchableOpacity>
                );
              })
            )}
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        {/* Header */}
        <View style={s.chatHeader}>
          <TouchableOpacity onPress={() => setActiveId(null)} style={{ marginRight: 10 }}>
            <Ionicons name="arrow-back" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={s.avatar}><Text style={s.avatarText}>{otherName[0]}</Text></View>
          <View style={{ flex: 1 }}>
            <Text style={s.headerName}>{otherName}</Text>
            {typing && typing !== user?.id ? <Text style={s.typingText}>typing…</Text> : null}
          </View>
        </View>

        {/* Messages */}
        <ScrollView ref={listRef} style={{ flex: 1, padding: 16 }} testID="messages-list">
          {messages.map(m => {
            const mine = m.sender_id === user?.id;
            return (
              <View key={m.id} style={[s.msgRow, mine ? { justifyContent: 'flex-end' } : { justifyContent: 'flex-start' }]}>
                <View style={[s.msgBubble, mine && s.msgMine]}>
                  <Text style={s.msgText}>{m.text}</Text>
                </View>
              </View>
            );
          })}
        </ScrollView>

        {/* Input */}
        <View style={s.inputBar}>
          <TextInput
            testID="message-input"
            style={s.msgInput}
            placeholder="Type a message…"
            placeholderTextColor={colors.textDim}
            value={text}
            onChangeText={(v) => {
              setText(v);
              if (activeId) api.post(`/conversations/${activeId}/typing`, { is_typing: true }).catch(() => {});
            }}
          />
          <TouchableOpacity testID="send-message-btn" style={s.sendBtn} onPress={send}>
            <Ionicons name="send" size={16} color={colors.white} />
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg0 },
  scroll: { flex: 1 },
  content: { padding: 20 },
  convItem: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, paddingHorizontal: 14, borderBottomWidth: 1, borderBottomColor: colors.border },
  avatar: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.violet, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: colors.white, fontWeight: '600', fontSize: 14 },
  convName: { fontWeight: '500', fontSize: 13.5, color: colors.text },
  convLast: { fontSize: 11, color: colors.textDim, marginTop: 2 },
  badge: { backgroundColor: colors.violet3, borderRadius: 999, paddingHorizontal: 7, paddingVertical: 1, minWidth: 20, alignItems: 'center' },
  badgeText: { color: colors.white, fontSize: 10.5 },
  chatHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border },
  headerName: { fontWeight: '500', color: colors.text },
  typingText: { fontSize: 11, color: colors.textDim },
  msgRow: { flexDirection: 'row', marginBottom: 8 },
  msgBubble: { maxWidth: '75%', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 10 },
  msgMine: { backgroundColor: colors.violet, borderColor: 'transparent' },
  msgText: { fontSize: 13.5, color: colors.text },
  inputBar: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14, borderTopWidth: 1, borderTopColor: colors.border },
  msgInput: { flex: 1, backgroundColor: 'rgba(10,12,26,0.65)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 10, color: colors.text, fontSize: 14 },
  sendBtn: { backgroundColor: colors.violet, width: 44, height: 44, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
});
