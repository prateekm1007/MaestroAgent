/**
 * WhisperTranscriber — in-browser speech-to-text using Transformers.js.
 *
 * This replaces the stub transcription in the backend CopilotSession.
 * Audio is captured locally (offscreen.js), then transcribed IN THE BROWSER
 * using a Whisper model loaded via Transformers.js (Hugging Face).
 * Only the text transcript is sent to the backend — audio NEVER leaves the device.
 *
 * Privacy-first: the model runs locally in the browser via WebGPU/WASM.
 * No audio data is sent over the network. Only JSON transcript chunks.
 *
 * Usage (from offscreen.js):
 *   const transcriber = new WhisperTranscriber();
 *   await transcriber.load();  // loads model (~40MB, cached after first load)
 *   const transcript = await transcriber.transcribe(audioBlob);
 *   // transcript = { text: "We will deliver SSO by Friday", ... }
 *
 * Model: openai/whisper-tiny.en (39MB) for English, or whisper-base (74MB)
 * for multi-language. The model is downloaded once and cached by the browser.
 *
 * Dependencies: @xenova/transformers (Transformers.js — runs ONNX models
 * in the browser via WebAssembly/WebGPU). This is the Hugging Face
 * "Transformers.js" library, NOT the Python transformers library.
 */

class WhisperTranscriber {
  constructor(modelName = "Xenova/whisper-tiny.en") {
    this.modelName = modelName;
    this.pipeline = null;
    this.isLoaded = false;
    this.isLoading = false;
    this.loadProgress = 0;
  }

  /**
   * Load the Whisper model. Called once; cached by the browser.
   * @returns {Promise<void>}
   */
  async load() {
    if (this.isLoaded || this.isLoading) return;

    this.isLoading = true;
    try {
      // Dynamic import — only loads the library when transcription is needed
      const { pipeline } = await import(
        "https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2"
      );

      this.pipeline = await pipeline("automatic-speech-recognition", this.modelName, {
        progress_callback: (progress) => {
          if (progress.status === "progress") {
            this.loadProgress = Math.round(progress.progress * 100);
            console.log(`Whisper model loading: ${this.loadProgress}%`);
          }
        },
      });

      this.isLoaded = true;
      this.isLoading = false;
      console.log("WhisperTranscriber: model loaded successfully");
    } catch (err) {
      this.isLoading = false;
      console.error("WhisperTranscriber: failed to load model:", err);
      throw new Error(`Whisper model load failed: ${err.message}`);
    }
  }

  /**
   * Transcribe an audio blob to text.
   * Audio is processed LOCALLY — never sent over the network.
   * @param {Blob} audioBlob — audio data (WebM/Opus from MediaRecorder)
   * @returns {Promise<{text: string, chunks: Array, language: string}>}
   */
  async transcribe(audioBlob) {
    if (!this.isLoaded) {
      await this.load();
    }

    try {
      // Convert blob to AudioBuffer for processing
      const audioContext = new AudioContext({ sampleRate: 16000 });
      const arrayBuffer = await audioBlob.arrayBuffer();
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

      // Get mono channel data at 16kHz (Whisper requirement)
      const audioData = this._getMonoAudio(audioBuffer, 16000);

      // Run transcription (local — model runs in browser via WASM)
      const output = await this.pipeline(audioData);

      // Clean up audio context
      audioContext.close();

      return {
        text: output.text || "",
        chunks: output.chunks || [],
        language: this.modelName.includes(".en") ? "english" : "multi",
        timestamp: Date.now(),
      };
    } catch (err) {
      console.error("WhisperTranscriber: transcription failed:", err);
      return {
        text: "",
        chunks: [],
        language: "unknown",
        error: err.message,
        timestamp: Date.now(),
      };
    }
  }

  /**
   * Transcribe a continuous audio stream (for real-time use).
   * Calls onTranscript for each chunk.
   * @param {MediaStream} stream — audio stream from getUserMedia/getDisplayMedia
   * @param {function} onTranscript — callback({text, isFinal, timestamp})
   * @param {object} options — { chunkDurationMs: 3000 }
   * @returns {Promise<void>}
   */
  async transcribeStream(stream, onTranscript, options = {}) {
    const chunkDurationMs = options.chunkDurationMs || 3000;
    const mediaRecorder = new MediaRecorder(stream, {
      mimeType: "audio/webm;codecs=opus",
      audioBitsPerSecond: 16000,
    });

    let chunkIndex = 0;

    mediaRecorder.ondataavailable = async (event) => {
      if (event.data.size > 0) {
        try {
          const result = await this.transcribe(event.data);
          if (result.text && result.text.trim()) {
            onTranscript({
              text: result.text.trim(),
              isFinal: false,
              chunkIndex: chunkIndex++,
              timestamp: result.timestamp,
            });
          }
        } catch (err) {
          console.warn("WhisperTranscriber: stream chunk transcription failed:", err);
        }
      }
    };

    mediaRecorder.start(chunkDurationMs);
    console.log(`WhisperTranscriber: stream transcription started (chunk: ${chunkDurationMs}ms)`);

    // Return a stop function
    return {
      stop: () => {
        mediaRecorder.stop();
        console.log("WhisperTranscriber: stream transcription stopped");
      },
    };
  }

  /**
   * Extract mono audio at the target sample rate.
   * @param {AudioBuffer} audioBuffer
   * @param {number} targetSampleRate
   * @returns {Float32Array} — mono audio data at target sample rate
   */
  _getMonoAudio(audioBuffer, targetSampleRate) {
    const numChannels = audioBuffer.numberOfChannels;
    const length = audioBuffer.length;
    const sampleRate = audioBuffer.sampleRate;

    // Mix down to mono
    const mono = new Float32Array(length);
    for (let channel = 0; channel < numChannels; channel++) {
      const channelData = audioBuffer.getChannelData(channel);
      for (let i = 0; i < length; i++) {
        mono[i] += channelData[i] / numChannels;
      }
    }

    // Resample if needed (simple linear interpolation)
    if (sampleRate !== targetSampleRate) {
      const ratio = sampleRate / targetSampleRate;
      const newLength = Math.floor(length / ratio);
      const resampled = new Float32Array(newLength);
      for (let i = 0; i < newLength; i++) {
        const srcIndex = i * ratio;
        const srcFloor = Math.floor(srcIndex);
        const srcCeil = Math.min(srcFloor + 1, length - 1);
        const fraction = srcIndex - srcFloor;
        resampled[i] = mono[srcFloor] * (1 - fraction) + mono[srcCeil] * fraction;
      }
      return resampled;
    }

    return mono;
  }

  /**
   * Get the current load status.
   */
  getStatus() {
    return {
      isLoaded: this.isLoaded,
      isLoading: this.isLoading,
      loadProgress: this.loadProgress,
      modelName: this.modelName,
    };
  }
}

// Export for use in offscreen.js
if (typeof module !== "undefined" && module.exports) {
  module.exports = WhisperTranscriber;
}
