// PDF.js worker setup
if (window.pdfjsLib) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdfjs/pdf.worker.min.js";
}

const pdfFileInput = document.getElementById("pdfFile");
const pdfStatus = document.getElementById("pdfStatus");
const textArea = document.getElementById("textArea");
const clearBtn = document.getElementById("clearBtn");

const engineSelect = document.getElementById("engineSelect");
const engineStatus = document.getElementById("engineStatus");
const voicevoxHint = document.getElementById("voicevoxHint");
const browserVoiceField = document.getElementById("browserVoiceField");
const voicevoxVoiceField = document.getElementById("voicevoxVoiceField");
const voicevoxSpeakerSelect = document.getElementById("voicevoxSpeakerSelect");

const voiceSelect = document.getElementById("voiceSelect");
const rateInput = document.getElementById("rate");
const pitchInput = document.getElementById("pitch");
const volumeInput = document.getElementById("volume");
const rateValue = document.getElementById("rateValue");
const pitchValue = document.getElementById("pitchValue");
const volumeValue = document.getElementById("volumeValue");

const playBtn = document.getElementById("playBtn");
const playFromHereBtn = document.getElementById("playFromHereBtn");
const pauseBtn = document.getElementById("pauseBtn");
const stopBtn = document.getElementById("stopBtn");
const playStatus = document.getElementById("playStatus");

const synth = window.speechSynthesis;
const VOICEVOX_URL = "http://localhost:50021";

let voices = [];
let chunks = [];
let chunkIndex = 0;
let isPaused = false;
let keepAliveTimer = null;

// VOICEVOX playback state. playbackToken invalidates in-flight synthesis
// requests when the user stops or restarts, so a late response never
// resumes audio the user already cancelled.
let playbackToken = 0;
let currentAudio = null;
let synthCache = new Map();
let voicevoxSpeakersLoaded = false;

function currentEngine() {
  return engineSelect.value;
}

// --- PDF extraction ---

pdfFileInput.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  if (!window.pdfjsLib) {
    pdfStatus.textContent = "PDF読み込みライブラリを取得できませんでした。ネットワーク接続を確認してください。";
    return;
  }

  pdfStatus.textContent = "PDFを読み込み中...";
  try {
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    let fullText = "";

    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
      pdfStatus.textContent = `PDFを読み込み中... (${pageNum}/${pdf.numPages}ページ)`;
      const page = await pdf.getPage(pageNum);
      const content = await page.getTextContent();
      let pageText = "";
      for (const item of content.items) {
        pageText += item.str;
        pageText += item.hasEOL ? "\n" : " ";
      }
      fullText += pageText.trim() + "\n\n";
    }

    textArea.value = fullText.trim();
    pdfStatus.textContent = `完了: ${pdf.numPages}ページを読み込みました（${file.name}）`;
  } catch (err) {
    console.error(err);
    pdfStatus.textContent = `PDFの読み込みに失敗しました: ${err.message}`;
  }
});

clearBtn.addEventListener("click", () => {
  textArea.value = "";
  pdfFileInput.value = "";
  pdfStatus.textContent = "";
  stopSpeaking();
});

// --- Voice list ---

function populateVoices() {
  voices = synth.getVoices();
  const previousValue = voiceSelect.value;
  voiceSelect.innerHTML = "";

  // Prefer Japanese voices first, but list everything.
  const sorted = [...voices].sort((a, b) => {
    const aJa = a.lang.startsWith("ja") ? 0 : 1;
    const bJa = b.lang.startsWith("ja") ? 0 : 1;
    if (aJa !== bJa) return aJa - bJa;
    return a.name.localeCompare(b.name);
  });

  sorted.forEach((voice) => {
    const option = document.createElement("option");
    option.value = voice.name;
    option.textContent = `${voice.name} (${voice.lang})`;
    voiceSelect.appendChild(option);
  });

  if (previousValue && sorted.some((v) => v.name === previousValue)) {
    voiceSelect.value = previousValue;
  }

  if (sorted.length === 0) {
    const option = document.createElement("option");
    option.textContent = "利用可能な音声が見つかりません";
    voiceSelect.appendChild(option);
  }
}

populateVoices();
if (synth.onvoiceschanged !== undefined) {
  synth.onvoiceschanged = populateVoices;
}

// --- VOICEVOX ---
// Talks to a locally running VOICEVOX engine. Its default CORS mode
// ("localapps") already allows localhost origins, so no extra setup is
// needed as long as this page is served over http://localhost.

async function loadVoicevoxSpeakers() {
  engineStatus.textContent = "VOICEVOXに接続中...";
  voicevoxSpeakerSelect.innerHTML = "";

  let speakers;
  try {
    const res = await fetch(`${VOICEVOX_URL}/speakers`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    speakers = await res.json();
  } catch (err) {
    voicevoxSpeakersLoaded = false;
    engineStatus.textContent =
      "VOICEVOXに接続できませんでした。VOICEVOXを起動してから、エンジンを選び直してください。";
    return false;
  }

  for (const speaker of speakers) {
    for (const style of speaker.styles) {
      const option = document.createElement("option");
      option.value = style.id;
      option.textContent = `${speaker.name}（${style.name}）`;
      voicevoxSpeakerSelect.appendChild(option);
    }
  }

  voicevoxSpeakersLoaded = voicevoxSpeakerSelect.options.length > 0;
  engineStatus.textContent = voicevoxSpeakersLoaded
    ? `VOICEVOXに接続しました（${voicevoxSpeakerSelect.options.length}種類の音声）`
    : "VOICEVOXに音声が見つかりませんでした。";
  return voicevoxSpeakersLoaded;
}

function clearSynthCache() {
  synthCache.clear();
}

async function synthesizeVoicevox(text) {
  const speaker = encodeURIComponent(voicevoxSpeakerSelect.value);

  const queryRes = await fetch(
    `${VOICEVOX_URL}/audio_query?speaker=${speaker}&text=${encodeURIComponent(text)}`,
    { method: "POST" }
  );
  if (!queryRes.ok) throw new Error(`audio_query HTTP ${queryRes.status}`);
  const query = await queryRes.json();

  query.speedScale = parseFloat(rateInput.value);
  // The pitch slider is 0-2 centred on 1; VOICEVOX accepts -0.15 to 0.15.
  const pitchScale = (parseFloat(pitchInput.value) - 1) * 0.15;
  query.pitchScale = Math.max(-0.15, Math.min(0.15, pitchScale));

  const synthRes = await fetch(`${VOICEVOX_URL}/synthesis?speaker=${speaker}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(query),
  });
  if (!synthRes.ok) throw new Error(`synthesis HTTP ${synthRes.status}`);
  return synthRes.blob();
}

function getSynthesized(index) {
  if (!synthCache.has(index)) {
    synthCache.set(index, synthesizeVoicevox(chunks[index]));
  }
  return synthCache.get(index);
}

async function playVoicevoxChunk(token) {
  if (token !== playbackToken) return;
  if (chunkIndex >= chunks.length) {
    finishSpeaking();
    return;
  }

  playStatus.textContent = `音声を生成中... (${chunkIndex + 1} / ${chunks.length})`;

  let blob;
  try {
    blob = await getSynthesized(chunkIndex);
  } catch (err) {
    if (token !== playbackToken) return;
    console.error(err);
    finishSpeaking(`VOICEVOXでの音声生成に失敗しました（${err.message}）。VOICEVOXが起動しているか確認してください。`);
    return;
  }
  if (token !== playbackToken) return;

  // Synthesis is slow enough to hear between chunks, so start the next one
  // while the current chunk plays.
  if (chunkIndex + 1 < chunks.length) {
    getSynthesized(chunkIndex + 1).catch(() => {});
  }

  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  audio.volume = parseFloat(volumeInput.value);
  currentAudio = audio;

  audio.onended = () => {
    URL.revokeObjectURL(url);
    if (token !== playbackToken) return;
    synthCache.delete(chunkIndex);
    chunkIndex++;
    playVoicevoxChunk(token);
  };
  audio.onerror = () => {
    URL.revokeObjectURL(url);
    if (token !== playbackToken) return;
    finishSpeaking("音声の再生に失敗しました");
  };

  updatePlayStatus();
  try {
    await audio.play();
  } catch (err) {
    if (token !== playbackToken) return;
    console.error(err);
    finishSpeaking(`再生できませんでした（${err.message}）`);
  }
}

engineSelect.addEventListener("change", async () => {
  stopSpeaking();
  playStatus.textContent = "";
  const useVoicevox = currentEngine() === "voicevox";
  browserVoiceField.hidden = useVoicevox;
  voicevoxVoiceField.hidden = !useVoicevox;
  voicevoxHint.hidden = !useVoicevox;
  clearSynthCache();

  if (useVoicevox) {
    await loadVoicevoxSpeakers();
  } else {
    engineStatus.textContent = "";
  }
});

voicevoxSpeakerSelect.addEventListener("change", clearSynthCache);

// --- Slider labels ---

rateInput.addEventListener("input", () => {
  rateValue.textContent = rateInput.value;
  clearSynthCache();
});
pitchInput.addEventListener("input", () => {
  pitchValue.textContent = pitchInput.value;
  clearSynthCache();
});
volumeInput.addEventListener("input", () => {
  volumeValue.textContent = volumeInput.value;
  if (currentAudio) currentAudio.volume = parseFloat(volumeInput.value);
});

// --- Text chunking ---
// Long single utterances can stall in some browsers (notably Chrome),
// so split into sentence-sized chunks and queue them one at a time.

function splitIntoChunks(text) {
  const normalized = text.replace(/\s+\n/g, "\n").trim();
  if (!normalized) return [];

  // Split on Japanese/English sentence terminators, keeping the terminator.
  const sentences = normalized.split(/(?<=[。.!?！?\n])\s*/).filter((s) => s.trim());

  const MAX_LEN = 200;
  const result = [];
  let buffer = "";

  for (const sentence of sentences) {
    const candidate = buffer ? buffer + " " + sentence : sentence;
    if (candidate.length > MAX_LEN && buffer) {
      result.push(buffer);
      buffer = sentence;
    } else {
      buffer = candidate;
    }
  }
  if (buffer.trim()) result.push(buffer);

  return result;
}

// --- Playback ---

function getSelectedVoice() {
  return voices.find((v) => v.name === voiceSelect.value) || null;
}

function speakNextChunk() {
  if (chunkIndex >= chunks.length) {
    finishSpeaking();
    return;
  }

  const utterance = new SpeechSynthesisUtterance(chunks[chunkIndex]);
  const voice = getSelectedVoice();
  if (voice) utterance.voice = voice;
  utterance.rate = parseFloat(rateInput.value);
  utterance.pitch = parseFloat(pitchInput.value);
  utterance.volume = parseFloat(volumeInput.value);

  utterance.onend = () => {
    chunkIndex++;
    updatePlayStatus();
    speakNextChunk();
  };
  utterance.onerror = (e) => {
    if (e.error === "interrupted" || e.error === "canceled") return;
    console.error("SpeechSynthesis error:", e.error);
    synth.cancel();
    finishSpeaking(`エラーが発生しました: ${e.error}`);
  };

  synth.speak(utterance);
}

function updatePlayStatus() {
  if (chunks.length === 0) {
    playStatus.textContent = "";
    return;
  }
  playStatus.textContent = `読み上げ中... (${Math.min(chunkIndex + 1, chunks.length)} / ${chunks.length})`;
}

function startKeepAlive() {
  // Chrome pauses speechSynthesis after ~15s of inactivity; nudging it
  // with pause/resume keeps long sessions from silently stalling.
  stopKeepAlive();
  keepAliveTimer = setInterval(() => {
    if (synth.speaking && !synth.paused) {
      synth.pause();
      synth.resume();
    }
  }, 10000);
}

function stopKeepAlive() {
  if (keepAliveTimer) {
    clearInterval(keepAliveTimer);
    keepAliveTimer = null;
  }
}

function finishSpeaking(message) {
  stopKeepAlive();
  playBtn.disabled = false;
  pauseBtn.disabled = true;
  stopBtn.disabled = true;
  playStatus.textContent = message !== undefined ? message : chunks.length ? "読み上げが完了しました" : "";
  chunks = [];
  chunkIndex = 0;
  isPaused = false;
  currentAudio = null;
}

function cancelAudio() {
  // Bump the token first so any in-flight synthesis resolves into a no-op.
  playbackToken++;
  synth.cancel();
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  clearSynthCache();
}

function stopSpeaking() {
  cancelAudio();
  finishSpeaking("停止しました");
}

function setPlayingControls() {
  if (currentEngine() === "browser") startKeepAlive();
  playBtn.disabled = true;
  pauseBtn.disabled = false;
  stopBtn.disabled = false;
  updatePlayStatus();
}

function beginPlayback(text) {
  cancelAudio();
  chunks = splitIntoChunks(text);
  chunkIndex = 0;
  isPaused = false;
  if (chunks.length === 0) {
    playStatus.textContent = "読み上げるテキストがありません";
    return;
  }

  if (currentEngine() === "voicevox") {
    if (!voicevoxSpeakersLoaded) {
      chunks = [];
      playStatus.textContent = "VOICEVOXに接続できていません。VOICEVOXを起動してから、エンジンを選び直してください。";
      return;
    }
    setPlayingControls();
    playVoicevoxChunk(playbackToken);
    return;
  }

  speakNextChunk();
  setPlayingControls();
}

playBtn.addEventListener("click", () => {
  if (isPaused) {
    isPaused = false;
    if (currentEngine() === "voicevox") {
      if (currentAudio) currentAudio.play().catch(() => {});
    } else {
      synth.resume();
    }
    setPlayingControls();
    return;
  }
  beginPlayback(textArea.value.trim());
});

playFromHereBtn.addEventListener("click", () => {
  const startPos = textArea.selectionStart || 0;
  const text = textArea.value.slice(startPos).trim();
  if (!text) {
    playStatus.textContent = "読み上げる位置を選択してください（テキスト欄をクリックしてカーソルを置く）";
    return;
  }
  beginPlayback(text);
});

pauseBtn.addEventListener("click", () => {
  if (currentEngine() === "voicevox") {
    if (currentAudio) currentAudio.pause();
  } else {
    synth.pause();
  }
  stopKeepAlive();
  isPaused = true;
  playBtn.disabled = false;
  pauseBtn.disabled = true;
  playStatus.textContent = "一時停止中";
});

stopBtn.addEventListener("click", () => {
  stopSpeaking();
});

window.addEventListener("beforeunload", () => {
  cancelAudio();
});
