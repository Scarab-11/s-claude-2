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
const browserVoiceHint = document.getElementById("browserVoiceHint");
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

const exportFormat = document.getElementById("exportFormat");
const exportBtn = document.getElementById("exportBtn");
const exportCancelBtn = document.getElementById("exportCancelBtn");
const exportStatus = document.getElementById("exportStatus");

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

// Edge exposes its cloud neural voices as e.g. "Microsoft Nanami Online
// (Natural) - Japanese (Japan)", which sound far better than the local
// SAPI voices. Remote voices in general (localService === false) are the
// cloud-synthesised ones, so treat both as the high-quality tier.
function isHighQualityVoice(voice) {
  return /natural|neural/i.test(voice.name) || voice.localService === false;
}

function isJapaneseVoice(voice) {
  return voice.lang.toLowerCase().startsWith("ja");
}

function populateVoices() {
  voices = synth.getVoices();
  const previousValue = voiceSelect.value;
  voiceSelect.innerHTML = "";

  // Japanese before other languages, and within each the high-quality
  // voices first, so the best choice is the one already selected.
  const rank = (v) => (isJapaneseVoice(v) ? 0 : 2) + (isHighQualityVoice(v) ? 0 : 1);
  const sorted = [...voices].sort((a, b) => {
    if (rank(a) !== rank(b)) return rank(a) - rank(b);
    return a.name.localeCompare(b.name);
  });

  sorted.forEach((voice) => {
    const option = document.createElement("option");
    option.value = voice.name;
    const badge = isHighQualityVoice(voice) ? "【高音質】" : "";
    option.textContent = `${badge}${voice.name} (${voice.lang})`;
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

  updateBrowserVoiceHint(sorted);
}

function updateBrowserVoiceHint(sorted) {
  const japaneseHq = sorted.filter((v) => isJapaneseVoice(v) && isHighQualityVoice(v));
  browserVoiceHint.textContent = japaneseHq.length
    ? `高音質な日本語音声が ${japaneseHq.length} 件見つかりました（一覧の先頭、【高音質】付き）。`
    : "高音質な日本語音声が見つかりませんでした。Microsoft Edge で開くと「Online (Natural)」の音声が使える場合があります（ネット接続が必要）。";
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
  browserVoiceHint.hidden = useVoicevox;
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

// --- Export to an audio file ---
// Only possible with VOICEVOX: the Web Speech API plays straight to the
// output device and never exposes the samples, so there is nothing to save.

let exportCancelled = false;
let exporting = false;

function parseWav(arrayBuffer) {
  const view = new DataView(arrayBuffer);
  const tag = (offset) => String.fromCharCode(
    view.getUint8(offset), view.getUint8(offset + 1),
    view.getUint8(offset + 2), view.getUint8(offset + 3)
  );

  if (tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new Error("WAV形式ではありません");

  let channels = 1;
  let sampleRate = 24000;
  let bitsPerSample = 16;
  let samples = null;

  // Walk the chunk list rather than assuming fixed offsets: engines are
  // free to insert LIST/fact chunks before the data.
  let offset = 12;
  while (offset + 8 <= view.byteLength) {
    const id = tag(offset);
    const size = view.getUint32(offset + 4, true);
    const body = offset + 8;

    if (id === "fmt ") {
      channels = view.getUint16(body + 2, true);
      sampleRate = view.getUint32(body + 4, true);
      bitsPerSample = view.getUint16(body + 14, true);
    } else if (id === "data") {
      const length = Math.min(size, view.byteLength - body);
      samples = new Int16Array(arrayBuffer.slice(body, body + length - (length % 2)));
    }

    offset = body + size + (size % 2);
  }

  if (!samples) throw new Error("WAVに音声データがありません");
  if (bitsPerSample !== 16) throw new Error(`未対応のビット深度です: ${bitsPerSample}`);
  return { channels, sampleRate, samples };
}

function buildWavHeader(dataBytes, channels, sampleRate) {
  const buffer = new ArrayBuffer(44);
  const view = new DataView(buffer);
  const writeTag = (offset, text) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  writeTag(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeTag(8, "WAVE");
  writeTag(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * channels * 2, true);
  view.setUint16(32, channels * 2, true);
  view.setUint16(34, 16, true);
  writeTag(36, "data");
  view.setUint32(40, dataBytes, true);
  return buffer;
}

function buildWavFile(pieces, channels, sampleRate) {
  const total = pieces.reduce((sum, p) => sum + p.length, 0);
  const header = buildWavHeader(total * 2, channels, sampleRate);
  return new Blob([header, ...pieces], { type: "audio/wav" });
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoke late: revoking immediately can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function exportFilename(extension) {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`;
  // Keep this ASCII: browsers drop a download name containing non-ASCII
  // characters and save the file as "download" with no extension.
  return `yomiage_${stamp}.${extension}`;
}

function setExporting(active) {
  exporting = active;
  exportBtn.disabled = active;
  exportCancelBtn.disabled = !active;
  exportFormat.disabled = active;
}

// Asks where to save before any synthesis happens. showSaveFilePicker
// needs transient user activation, and synthesising a book takes minutes,
// so the click that starts the export is the only moment it can be called.
async function chooseDestination(filename, asMp3) {
  if (!window.showSaveFilePicker) return null;

  const accept = asMp3 ? { "audio/mpeg": [".mp3"] } : { "audio/wav": [".wav"] };
  try {
    const handle = await window.showSaveFilePicker({
      suggestedName: filename,
      types: [{ description: asMp3 ? "MP3 音声" : "WAV 音声", accept }],
    });
    return { handle, writable: await handle.createWritable() };
  } catch (err) {
    if (err.name === "AbortError") return "cancelled";
    // Any other failure (permission, unsupported context) falls back to
    // an ordinary download rather than losing the export.
    console.warn("showSaveFilePicker unavailable, falling back to download:", err);
    return null;
  }
}

async function runExport() {
  if (currentEngine() !== "voicevox") {
    exportStatus.textContent =
      "音声ファイルの保存はVOICEVOX使用時のみ可能です。「読み上げエンジン」でVOICEVOXを選んでください。";
    return;
  }
  if (!voicevoxSpeakersLoaded) {
    exportStatus.textContent = "VOICEVOXに接続できていません。VOICEVOXを起動してから、エンジンを選び直してください。";
    return;
  }

  const parts = splitIntoChunks(textArea.value.trim());
  if (parts.length === 0) {
    exportStatus.textContent = "音声にするテキストがありません";
    return;
  }

  const asMp3 = exportFormat.value === "mp3";
  const extension = asMp3 ? "mp3" : "wav";
  const filename = exportFilename(extension);

  const destination = await chooseDestination(filename, asMp3);
  if (destination === "cancelled") {
    exportStatus.textContent = "保存をキャンセルしました";
    return;
  }
  const writable = destination ? destination.writable : null;
  const savedName = destination ? destination.handle.name : filename;

  // Exporting re-synthesises everything; stop playback so the two do not
  // compete for the engine.
  cancelAudio();
  finishSpeaking("");

  exportCancelled = false;
  setExporting(true);

  let encoder = null;
  let channels = 1;
  let sampleRate = 24000;
  let bytesWritten = 0;
  let pcmBytes = 0;
  const pieces = [];

  // With a file handle the data goes straight to disk, so a long book never
  // has to fit in memory; without one it is collected for a download.
  const emit = async (data) => {
    if (writable) {
      await writable.write(data);
      bytesWritten += data.byteLength !== undefined ? data.byteLength : data.length * 2;
    } else {
      pieces.push(data);
    }
  };

  try {
    for (let i = 0; i < parts.length; i++) {
      if (exportCancelled) {
        if (writable) await writable.abort();
        exportStatus.textContent = "中止しました";
        return;
      }
      exportStatus.textContent = `音声を作成中... (${i + 1} / ${parts.length})`;
      // Yield so the status text repaints between chunks.
      await new Promise((resolve) => setTimeout(resolve, 0));

      const blob = await synthesizeVoicevox(parts[i]);
      const wav = parseWav(await blob.arrayBuffer());

      if (i === 0) {
        channels = wav.channels;
        sampleRate = wav.sampleRate;
        if (asMp3) {
          if (!window.lamejs) throw new Error("MP3エンコーダを読み込めませんでした");
          encoder = new lamejs.Mp3Encoder(channels, sampleRate, 64);
        } else if (writable) {
          // Reserve the header; its sizes are patched in once the total is known.
          await writable.write(buildWavHeader(0, channels, sampleRate));
          bytesWritten += 44;
        }
      }

      if (asMp3) {
        // Encode as we go so only the (much smaller) MP3 data is retained.
        const BLOCK = 1152 * channels;
        for (let at = 0; at < wav.samples.length; at += BLOCK) {
          const block = wav.samples.subarray(at, Math.min(at + BLOCK, wav.samples.length));
          const encoded = encoder.encodeBuffer(block);
          if (encoded.length > 0) await emit(encoded);
        }
      } else {
        pcmBytes += wav.samples.byteLength;
        await emit(wav.samples);
      }
    }

    if (exportCancelled) {
      if (writable) await writable.abort();
      exportStatus.textContent = "中止しました";
      return;
    }

    if (asMp3) {
      const tail = encoder.flush();
      if (tail.length > 0) await emit(tail);
    }

    let size;
    if (writable) {
      if (!asMp3) {
        // Rewrite the header now that the data length is known.
        await writable.write({ type: "write", position: 0, data: buildWavHeader(pcmBytes, channels, sampleRate) });
      }
      await writable.close();
      size = bytesWritten;
    } else {
      const blob = asMp3
        ? new Blob(pieces, { type: "audio/mpeg" })
        : buildWavFile(pieces, channels, sampleRate);
      downloadBlob(blob, filename);
      size = blob.size;
    }

    const mb = (size / 1024 / 1024).toFixed(1);
    exportStatus.textContent = destination
      ? `完了: ${savedName} を保存しました（${mb} MB）`
      : `完了: ${savedName} をダウンロードしました（${mb} MB）`;
  } catch (err) {
    console.error(err);
    if (writable) await writable.abort().catch(() => {});
    exportStatus.textContent = `音声ファイルの作成に失敗しました: ${err.message}`;
  } finally {
    setExporting(false);
  }
}

exportBtn.addEventListener("click", runExport);

exportCancelBtn.addEventListener("click", () => {
  exportCancelled = true;
  exportStatus.textContent = "中止しています...";
});
