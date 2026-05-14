import { mkdirSync, writeFileSync } from "node:fs";

const sampleRate = 44100;
const seconds = 30;
const channels = 2;
const totalSamples = sampleRate * seconds;
const output = "public/music/farmtrack-demo-loop.wav";

const chords = [
  [146.83, 220, 293.66],
  [164.81, 246.94, 329.63],
  [130.81, 196, 261.63],
  [174.61, 261.63, 349.23],
];

const writeString = (view, offset, value) => {
  for (let i = 0; i < value.length; i += 1) {
    view.setUint8(offset + i, value.charCodeAt(i));
  }
};

const envelope = (time) => {
  const fadeIn = Math.min(time / 2.2, 1);
  const fadeOut = Math.min((seconds - time) / 2.6, 1);
  return Math.max(0, Math.min(fadeIn, fadeOut));
};

const soft = (x) => Math.tanh(x * 1.65);

const buffer = new ArrayBuffer(44 + totalSamples * channels * 2);
const view = new DataView(buffer);

writeString(view, 0, "RIFF");
view.setUint32(4, 36 + totalSamples * channels * 2, true);
writeString(view, 8, "WAVE");
writeString(view, 12, "fmt ");
view.setUint32(16, 16, true);
view.setUint16(20, 1, true);
view.setUint16(22, channels, true);
view.setUint32(24, sampleRate, true);
view.setUint32(28, sampleRate * channels * 2, true);
view.setUint16(32, channels * 2, true);
view.setUint16(34, 16, true);
writeString(view, 36, "data");
view.setUint32(40, totalSamples * channels * 2, true);

let offset = 44;
for (let i = 0; i < totalSamples; i += 1) {
  const time = i / sampleRate;
  const chord = chords[Math.floor(time / 3.75) % chords.length];
  const beat = time * 1.6;
  const pulse = Math.pow(Math.max(0, Math.sin(Math.PI * beat)), 9);
  const hat = Math.pow(Math.max(0, Math.sin(Math.PI * time * 6.4)), 18) * 0.035;
  const bassFreq = chord[0] / 2;

  let pad = 0;
  for (const [index, freq] of chord.entries()) {
    pad +=
      Math.sin(2 * Math.PI * freq * time + index * 0.3) * 0.09 +
      Math.sin(2 * Math.PI * freq * 2.01 * time) * 0.022;
  }

  const bass = Math.sin(2 * Math.PI * bassFreq * time) * pulse * 0.18;
  const shimmer = Math.sin(2 * Math.PI * (chord[2] * 2) * time) * 0.035 * Math.sin(time * 0.9);
  const sample = soft((pad + bass + shimmer + hat) * envelope(time));
  const left = Math.max(-1, Math.min(1, sample * 0.82));
  const right = Math.max(-1, Math.min(1, (sample + shimmer * 0.2) * 0.82));

  view.setInt16(offset, left * 32767, true);
  view.setInt16(offset + 2, right * 32767, true);
  offset += 4;
}

mkdirSync("public/music", { recursive: true });
writeFileSync(output, Buffer.from(buffer));
console.log(`Generated ${output}`);
