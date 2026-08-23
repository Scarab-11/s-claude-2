// PDF.js worker setup
if (window.pdfjsLib) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdfjs/pdf.worker.min.js";
}

const pdfFileInput = document.getElementById("pdfFile");
const pdfStatus = document.getElementById("pdfStatus");
const textArea = document.getElementById("textArea");
const clearBtn = document.getElementById("clearBtn");

const voiceSelect = document.getElementById("voiceSelect");
const rateInput = document.getElementById("rate");
const pitchInput = document.getElementById("pitch");
const volumeInput = document.getElementById("volume");
const rateValue = document.getElementById("rateValue");
const pitchValue = document.getElementById("pitchValue");
const volumeValue = document.getElementById("volumeValue");

const playBtn = document.getElementById("playBtn");
const pauseBtn = document.getElementById("pauseBtn");
const stopBtn = document.getElementById("stopBtn");
const playStatus = document.getElementById("playStatus");

const synth = window.speechSynthesis;
let voices = [];
let chunks = [];
let chunkIndex = 0;
let isPaused = false;
let keepAliveTimer = null;

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

// --- Slider labels ---

rateInput.addEventListener("input", () => {
  rateValue.textContent = rateInput.value;
});
pitchInput.addEventListener("input", () => {
  pitchValue.textContent = pitchInput.value;
});
volumeInput.addEventListener("input", () => {
  volumeValue.textContent = volumeInput.value;
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
}

function stopSpeaking() {
  synth.cancel();
  finishSpeaking("停止しました");
}

playBtn.addEventListener("click", () => {
  const text = textArea.value.trim();
  if (!text) {
    playStatus.textContent = "読み上げるテキストがありません";
    return;
  }

  if (isPaused) {
    synth.resume();
    isPaused = false;
  } else {
    synth.cancel();
    chunks = splitIntoChunks(text);
    chunkIndex = 0;
    if (chunks.length === 0) {
      playStatus.textContent = "読み上げるテキストがありません";
      return;
    }
    speakNextChunk();
  }

  startKeepAlive();
  playBtn.disabled = true;
  pauseBtn.disabled = false;
  stopBtn.disabled = false;
  updatePlayStatus();
});

pauseBtn.addEventListener("click", () => {
  synth.pause();
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
  synth.cancel();
});
