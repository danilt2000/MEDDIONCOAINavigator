import deleteIcon from '@material-symbols/svg-400/outlined/delete.svg?raw';
import micIcon from '@material-symbols/svg-400/outlined/mic.svg?raw';
import sendIcon from '@material-symbols/svg-400/outlined/send.svg?raw';
import stopIcon from '@material-symbols/svg-400/outlined/stop.svg?raw';
import volumeOffIcon from '@material-symbols/svg-400/outlined/volume_off.svg?raw';
import volumeUpIcon from '@material-symbols/svg-400/outlined/volume_up.svg?raw';
import { api, postSse, type ChatMessage, type LevelCard, type NavigatorReply } from '@navigator/api';
import {
  ChipSet,
  Dialog,
  FilledButton,
  FilledIconButton,
  FilterChip,
  IconButton,
  OutlinedTextField,
  SuggestionChip,
  SvgIcon,
  TextButton,
  TriageChip,
} from '@navigator/ui';
import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { callTargets, capitalize, formatDayTime, store, useApi, useApp, type CallTarget } from '../app-state';
import { format } from '../i18n';
import { AmbulanceAnd155, CallButtons } from '../ui';

interface UiMessage {
  id: string;
  role: 'user' | 'navigator';
  text: string;
  level_card?: LevelCard | null;
  followup_question?: string | null;
  pending?: boolean;
  failed?: { userId: string; text: string; payload: string };
}

interface SpeechEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}

interface Recognition {
  lang: string;
  interimResults: boolean;
  onresult: ((event: SpeechEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

const speechWindow = window as unknown as Record<string, (new () => Recognition) | undefined>;
const Recognizer = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;

const synth = window.speechSynthesis as SpeechSynthesis | undefined;

const voiceFor = (lang: string) => synth?.getVoices().find((voice) => voice.lang.toLowerCase().startsWith(lang));

// a phone number like 724 590 848 is read digit by digit, not as hundreds
const spokenText = (text: string) =>
  text.replace(/\b\d{3} \d{3}(?: \d{3})?\b/g, (phone) => phone.split(' ').map((group) => group.split('').join(' ')).join(', '));

function speak(text: string, voice: SpeechSynthesisVoice) {
  // one utterance per sentence: Chrome silently stops long utterances after about 15 s
  for (const sentence of spokenText(text).split(/(?<=[.!?])\s+/).filter(Boolean)) {
    const utterance = new SpeechSynthesisUtterance(sentence);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    synth?.speak(utterance);
  }
}

const stopSpeaking = () => synth?.cancel();

function useVoice(lang: string) {
  const [voice, setVoice] = useState(() => voiceFor(lang));
  useEffect(() => {
    const update = () => setVoice(voiceFor(lang));
    update();
    synth?.addEventListener('voiceschanged', update);
    return () => synth?.removeEventListener('voiceschanged', update);
  }, [lang]);
  return voice;
}

function useCardTargets(card: LevelCard): CallTarget[] {
  const { t, now, contacts } = useApp();
  return callTargets(card.uroven, now, contacts, t);
}

function NextStepCard({ card }: { card: LevelCard }) {
  const { lang, locale, t } = useApp();
  const targets = useCardTargets(card);
  return (
    <section className="next-step" data-level={card.uroven}>
      <TriageChip level={card.uroven} lang={lang} withStep />
      {card.kontakt && <p className="next-step-contact">{capitalize(card.kontakt)}</p>}
      {card.sla_do && <p className="small">{format(t.deadline, formatDayTime(new Date(card.sla_do), locale).toLowerCase())}</p>}
      <CallButtons targets={targets} />
    </section>
  );
}

const fieldValue = (event: Event) => (event.target as HTMLInputElement).value;

export function Navigator() {
  const { t, lang, patientId, caregiver, setCaregiver, forWhom } = useApp();
  const routeState = useLocation().state as { followup?: string; intro?: string; patientId?: string } | null;
  const followup = routeState?.patientId === patientId ? routeState.followup : undefined;
  const intro = routeState?.patientId === patientId ? routeState.intro : undefined;
  const historyPath = `/api/chat/${patientId}/messages`;
  const history = useApi<ChatMessage[]>(historyPath);
  const [clearing, setClearing] = useState(false);
  const [local, setLocal] = useState<UiMessage[]>(() =>
    followup
      ? [{ id: 'followup', role: 'navigator', text: followup, followup_question: followup }]
      : intro
        ? [{ id: 'intro', role: 'navigator', text: intro }]
        : [],
  );
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const recognition = useRef<Recognition | null>(null);
  const voice = useVoice(lang);
  const [voiceOn, setVoiceOn] = useState(() => store.get('voice', false));
  const aloud = Boolean(voice && voiceOn);
  const aloudRef = useRef(aloud);
  aloudRef.current = aloud;

  const messages: UiMessage[] = [
    { id: 'welcome', role: 'navigator', text: t.chatWelcome },
    ...(history.data ?? []).map((message) => ({ ...message })),
    ...local,
  ];
  const lastText = messages[messages.length - 1]?.text;
  useEffect(() => {
    scrollTo({ top: document.documentElement.scrollHeight });
  }, [messages.length, lastText]);
  useEffect(() => {
    const hide = () => document.hidden && stopSpeaking();
    document.addEventListener('visibilitychange', hide);
    return () => {
      document.removeEventListener('visibilitychange', hide);
      stopListening();
      stopSpeaking();
    };
  }, []);

  const card = [...messages].reverse().find((message) => message.level_card)?.level_card;
  const last = messages[messages.length - 1];
  const openQuestion = !busy && last.role === 'navigator' ? last.followup_question : null;
  const yesNoQuestion = openQuestion && !/^(kolik|koľk|kolk|jak|ako|kdy|kedy|co|čo|kde|kter|ktor|proč|prečo)/i.test(openQuestion.trim());
  const hasUserMessages = messages.some((message) => message.role === 'user');

  async function send(display: string, payload = display) {
    if (!display.trim() || busy) return;
    stopListening();
    stopSpeaking();
    // iOS speaks only after a first utterance started by a tap
    if (aloudRef.current) synth?.speak(new SpeechSynthesisUtterance(''));
    setText('');
    const userId = crypto.randomUUID();
    const replyId = crypto.randomUUID();
    const update = (patch: Partial<UiMessage>) =>
      setLocal((previous) => previous.map((message) => (message.id === replyId ? { ...message, ...patch } : message)));
    setLocal((previous) => [
      ...previous,
      { id: userId, role: 'user', text: display.trim() },
      { id: replyId, role: 'navigator', text: '', pending: true },
    ]);
    setBusy(true);
    let received = '';
    let done = false;
    let redSpoken = false;
    try {
      const body = { text: payload.trim(), author: caregiver ? 'pecujici' : 'pacient', lang };
      for await (const event of postSse(`/api/chat/${patientId}/stream`, body)) {
        if (event.event === 'card') {
          const levelCard = event.data as LevelCard;
          update({ level_card: levelCard });
          // the red instruction is spoken at once, before the answer that may take seconds
          if (aloudRef.current && voice && levelCard.uroven === 4 && !redSpoken) {
            redSpoken = true;
            stopSpeaking();
            speak(t.voiceRed, voice);
          }
        } else if (event.event === 'delta') {
          received += String(event.data);
          update({ text: received });
        } else if (event.event === 'done') {
          const reply = event.data as NavigatorReply;
          done = true;
          update({
            text: reply.reply_text || received,
            followup_question: reply.followup_question,
            ...(reply.level_card ? { level_card: reply.level_card } : {}),
          });
          if (aloudRef.current && voice) speak(reply.reply_text || received, voice);
        } else if (event.event === 'error') throw new Error(String(event.data));
      }
      if (!done && !received) throw new Error('empty reply');
      update({ pending: false });
    } catch {
      update({ pending: false, failed: { userId, text: display, payload } });
    } finally {
      setBusy(false);
    }
  }

  async function clearChat() {
    setClearing(false);
    await api.delete(historyPath);
    store.set(`cache:${historyPath}`, []);
    setLocal([]);
    history.reload();
  }

  const retry = (message: UiMessage) => {
    const failed = message.failed!;
    setLocal((previous) => previous.filter((item) => item.id !== message.id && item.id !== failed.userId));
    void send(failed.text, failed.payload);
  };

  function stopListening() {
    const current = recognition.current;
    recognition.current = null;
    current?.stop();
  }

  // in voice mode the end of speech sends the message; otherwise the text waits in the field
  const toggleMic = () => {
    if (listening) {
      recognition.current?.stop();
      return;
    }
    if (!Recognizer) return;
    stopSpeaking();
    const recognizer = new Recognizer();
    const prefix = text ? `${text} ` : '';
    let heard = '';
    recognizer.lang = lang === 'sk' ? 'sk-SK' : 'cs-CZ';
    recognizer.interimResults = true;
    recognizer.onresult = (event) => {
      heard = prefix + Array.from(event.results, (result) => result[0].transcript).join(' ');
      setText(heard);
    };
    recognizer.onend = () => {
      setListening(false);
      if (recognition.current !== recognizer) return;
      recognition.current = null;
      if (aloudRef.current && heard.trim()) void send(heard);
    };
    recognition.current = recognizer;
    recognizer.start();
    setListening(true);
  };

  const toggleVoice = () => {
    const on = !voiceOn;
    setVoiceOn(on);
    store.set('voice', on);
    stopSpeaking();
    if (on && voice) speak(t.voiceStarted, voice);
  };

  return (
    <main
      className="content chat"
      onClickCapture={(event) => {
        // a call button is a Material button whose href is a property, not an attribute
        if (event.nativeEvent.composedPath().some((node) => String((node as { href?: unknown }).href).startsWith('tel:'))) stopSpeaking();
      }}
    >
      <header className="chat-header">
        <div className="chat-title-row">
          <h1 className="title">{t.chatTitle}</h1>
          <span>
            {voice && (
              <IconButton
                aria-label={aloud ? t.voiceOff : t.voiceOn}
                title={aloud ? t.voiceOff : t.voiceOn}
                onClick={toggleVoice}
                className={aloud ? 'toggle-on' : undefined}
              >
                <SvgIcon svg={aloud ? volumeUpIcon : volumeOffIcon} />
              </IconButton>
            )}
            {hasUserMessages && (
              <IconButton aria-label={t.clearChat} title={t.clearChat} disabled={busy} onClick={() => setClearing(true)}>
                <SvgIcon svg={deleteIcon} />
              </IconButton>
            )}
          </span>
        </div>
        <p className="muted small">{t.chatSubtitle}</p>
        {aloud && <p className="muted small">{t.voiceNote}</p>}
        <ChipSet>
          <FilterChip
            label={caregiver ? format(t.writingFor, forWhom) : t.caregiverChip}
            selected={caregiver}
            onClick={() => setCaregiver(!caregiver)}
          />
        </ChipSet>
      </header>

      <Dialog open={clearing} onClosed={() => setClearing(false)}>
        <div slot="headline">{t.clearChat}</div>
        <div slot="content">{t.clearChatText}</div>
        <div slot="actions">
          <TextButton onClick={() => setClearing(false)}>{t.cancel}</TextButton>
          <FilledButton onClick={() => void clearChat()}>{t.clear}</FilledButton>
        </div>
      </Dialog>

      {card && card.uroven >= 2 && <NextStepCard card={card} />}

      <div className="messages" aria-live="polite">
        {messages.map((message) => (
          <div key={message.id} className={`bubble-row ${message.role}`}>
            <div className={`bubble ${message.role}`}>
              <span className="sr-only">{message.role === 'user' ? t.you : t.navigator}: </span>
              {message.level_card && message.role === 'navigator' && (
                <span className="bubble-card">
                  <TriageChip level={message.level_card.uroven} lang={lang} withStep />
                  {message.level_card.kontakt && <span className="small">{message.level_card.kontakt}</span>}
                </span>
              )}
              {message.text && <span className="bubble-text">{message.text}</span>}
              {message.pending && !message.text && (
                <span className="typing" aria-label="…">
                  <span />
                  <span />
                  <span />
                </span>
              )}
              {message.failed && (
                <span className="bubble-error" role="alert">
                  {t.chatError}
                  <TextButton onClick={() => retry(message)}>{t.retry}</TextButton>
                  <AmbulanceAnd155 />
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="composer-area">
        {yesNoQuestion ? (
          <ChipSet className="quick-replies">
            {[t.yes, t.no, t.dontKnow].map((answer) => (
              <SuggestionChip key={answer} label={answer} onClick={() => send(answer, `${answer} – ${yesNoQuestion}`)} />
            ))}
          </ChipSet>
        ) : (
          !hasUserMessages &&
          !openQuestion &&
          !intro &&
          !busy && (
            <ChipSet className="quick-replies">
              {[t.suggest1, t.suggest2, t.suggest3, t.suggest4].map((question) => (
                <SuggestionChip key={question} label={question} onClick={() => send(question)} />
              ))}
            </ChipSet>
          )
        )}
        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            void send(text);
          }}
        >
          <OutlinedTextField
            className="composer-input"
            label={t.inputLabel}
            type="textarea"
            rows={1}
            value={text}
            onInput={(event) => setText(fieldValue(event))}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void send(text);
              }
            }}
          />
          {Recognizer && (
            <IconButton type="button" aria-label={listening ? t.micStop : t.mic} onClick={toggleMic} className={listening ? 'toggle-on' : undefined}>
              <SvgIcon svg={listening ? stopIcon : micIcon} />
            </IconButton>
          )}
          <FilledIconButton type="submit" aria-label={t.send} disabled={busy || !text.trim()}>
            <SvgIcon svg={sendIcon} />
          </FilledIconButton>
        </form>
      </div>
    </main>
  );
}
