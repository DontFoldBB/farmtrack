import { Audio } from "@remotion/media";
import {
  AbsoluteFill,
  Easing,
  Img,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type Scene = {
  from: number;
  duration: number;
  eyebrow: string;
  title: string;
  detail: string;
  image: string;
  align: "left" | "right";
};

const scenes: Scene[] = [
  {
    from: 0,
    duration: 180,
    eyebrow: "Local desktop tracker",
    title: "Airdrop farming without spreadsheets",
    detail: "Protocols, balances, P&L, points, wallets and perp positions in one private desktop app.",
    image: "screenshots/main.png",
    align: "right",
  },
  {
    from: 170,
    duration: 165,
    eyebrow: "Protocols",
    title: "Track every campaign in one table",
    detail: "Deposit, balance, spent, withdrawn, points, status and $/point stay visible at a glance.",
    image: "screenshots/protocols.png",
    align: "left",
  },
  {
    from: 320,
    duration: 165,
    eyebrow: "Wallets",
    title: "Manage many wallets cleanly",
    detail: "Labels, protocol links and bulk imports keep address work organized across profiles.",
    image: "screenshots/wallets.png",
    align: "right",
  },
  {
    from: 470,
    duration: 165,
    eyebrow: "Weekly snapshots",
    title: "See progress by epoch",
    detail: "Break protocol work into weekly checkpoints and compare activity over time.",
    image: "screenshots/protocol-detail.png",
    align: "left",
  },
  {
    from: 620,
    duration: 170,
    eyebrow: "Perp monitor",
    title: "Live positions and liquidation alerts",
    detail: "HyperLiquid, Nado, Extended and Pacifica accounts with P&L, margin and Telegram reports.",
    image: "screenshots/perp.png",
    align: "right",
  },
];

const palette = {
  bg: "#201d1d",
  panel: "#282423",
  panel2: "#181514",
  text: "#efe7da",
  muted: "#a79d90",
  border: "#4d463e",
  green: "#7fd19b",
  amber: "#d6aa66",
  red: "#e06c75",
};

const ease = Easing.bezier(0.16, 1, 0.3, 1);

const clamp = {
  extrapolateLeft: "clamp" as const,
  extrapolateRight: "clamp" as const,
};

const progress = (frame: number, start: number, end: number) =>
  interpolate(frame, [start, end], [0, 1], { ...clamp, easing: ease });

const SceneCard = ({ scene }: { scene: Scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const intro = progress(frame, 0, fps);
  const outro = interpolate(frame, [scene.duration - 24, scene.duration], [1, 0], clamp);
  const visible = Math.min(intro, outro);
  const mediaX = interpolate(intro, [0, 1], [scene.align === "right" ? 70 : -70, 0], clamp);
  const copyX = interpolate(intro, [0, 1], [scene.align === "right" ? -38 : 38, 0], clamp);
  const zoom = interpolate(frame, [0, scene.duration], [1.02, 1.075], clamp);

  const copy = (
    <div
      style={{
        width: 590,
        transform: `translateX(${copyX}px)`,
        opacity: visible,
      }}
    >
      <div style={styles.eyebrow}>{scene.eyebrow}</div>
      <h1 style={styles.sceneTitle}>{scene.title}</h1>
      <p style={styles.sceneDetail}>{scene.detail}</p>
    </div>
  );

  const media = (
    <div
      style={{
        ...styles.screenshotShell,
        transform: `translateX(${mediaX}px)`,
        opacity: visible,
      }}
    >
      <div style={styles.windowBar}>
        <span style={{ ...styles.dot, backgroundColor: palette.red }} />
        <span style={{ ...styles.dot, backgroundColor: palette.amber }} />
        <span style={{ ...styles.dot, backgroundColor: palette.green }} />
        <span style={styles.windowLabel}>FarmTrack</span>
      </div>
      <div style={styles.screenshotMask}>
        <Img
          src={staticFile(scene.image)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${zoom})`,
          }}
        />
      </div>
    </div>
  );

  return (
    <AbsoluteFill style={styles.scene}>
      {scene.align === "left" ? media : copy}
      {scene.align === "left" ? copy : media}
    </AbsoluteFill>
  );
};

const Opening = () => {
  const frame = useCurrentFrame();
  const logo = progress(frame, 8, 42);
  const title = progress(frame, 28, 72);
  const screenshot = progress(frame, 62, 116);
  const lift = interpolate(screenshot, [0, 1], [48, 0], clamp);

  return (
    <AbsoluteFill style={styles.opening}>
      <div style={{ ...styles.logoWrap, opacity: logo }}>
        <Img src={staticFile("brand/farmtrack-wordmark.svg")} style={styles.logo} />
      </div>
      <div
        style={{
          ...styles.openingCopy,
          opacity: title,
          transform: `translateY(${interpolate(title, [0, 1], [34, 0], clamp)}px)`,
        }}
      >
        <h1 style={styles.openingTitle}>Local crypto farming dashboard</h1>
        <p style={styles.openingDetail}>Private SQLite profiles. Desktop window. No accounts. No cloud.</p>
      </div>
      <div
        style={{
          ...styles.heroScreenshot,
          opacity: screenshot,
          transform: `translateY(${lift}px) scale(${interpolate(screenshot, [0, 1], [0.96, 1], clamp)})`,
        }}
      >
        <Img src={staticFile("screenshots/main.png")} style={styles.heroImage} />
      </div>
    </AbsoluteFill>
  );
};

const Closing = () => {
  const frame = useCurrentFrame();
  const enter = progress(frame, 0, 45);
  const badges = progress(frame, 55, 105);

  return (
    <AbsoluteFill style={styles.closing}>
      <div style={{ ...styles.logoWrap, opacity: enter }}>
        <Img src={staticFile("brand/farmtrack-wordmark.svg")} style={styles.logo} />
      </div>
      <h1
        style={{
          ...styles.finalTitle,
          opacity: enter,
          transform: `translateY(${interpolate(enter, [0, 1], [32, 0], clamp)}px)`,
        }}
      >
        Built for local-first airdrop tracking
      </h1>
      <div style={{ ...styles.badges, opacity: badges }}>
        {["Python + Flask", "pywebview", "SQLite profiles", "255 tests"].map((label) => (
          <span key={label} style={styles.badge}>
            {label}
          </span>
        ))}
      </div>
      <p style={{ ...styles.repoLine, opacity: progress(frame, 108, 142) }}>
        github.com/DontFoldBB/farmtrack
      </p>
    </AbsoluteFill>
  );
};

const Timeline = () => {
  const frame = useCurrentFrame();
  const active = scenes.findIndex((scene) => frame >= scene.from && frame < scene.from + scene.duration);
  const width = interpolate(frame, [0, 900], [0, 100], clamp);

  return (
    <div style={styles.timelineWrap}>
      <div style={styles.timelineTrack}>
        <div style={{ ...styles.timelineProgress, width: `${width}%` }} />
      </div>
      <div style={styles.navDots}>
        {scenes.map((scene, index) => (
          <span
            key={scene.title}
            style={{
              ...styles.navDot,
              backgroundColor: index === active ? palette.green : palette.border,
            }}
          />
        ))}
      </div>
    </div>
  );
};

export const FarmTrackGithubDemo = () => {
  return (
    <AbsoluteFill style={styles.root}>
      <Audio
        src={staticFile("music/farmtrack-demo-loop.wav")}
        volume={(frame) => {
          const fadeIn = interpolate(frame, [0, 45], [0, 0.42], clamp);
          const fadeOut = interpolate(frame, [840, 900], [0.42, 0], clamp);
          return Math.min(fadeIn, fadeOut);
        }}
      />
      <BackgroundGrid />
      <Sequence from={0} durationInFrames={170} premountFor={30}>
        <Opening />
      </Sequence>
      {scenes.slice(1).map((scene) => (
        <Sequence key={scene.title} from={scene.from} durationInFrames={scene.duration} premountFor={30}>
          <SceneCard scene={scene} />
        </Sequence>
      ))}
      <Sequence from={790} durationInFrames={110} premountFor={30}>
        <Closing />
      </Sequence>
      <Timeline />
    </AbsoluteFill>
  );
};

const BackgroundGrid = () => {
  const frame = useCurrentFrame();
  const drift = frame * 0.18;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: palette.bg,
        backgroundImage:
          `linear-gradient(rgba(127, 209, 155, 0.065) 1px, transparent 1px),` +
          `linear-gradient(90deg, rgba(127, 209, 155, 0.055) 1px, transparent 1px)`,
        backgroundSize: "64px 64px",
        backgroundPosition: `${drift}px ${drift * 0.55}px`,
      }}
    >
      <div style={styles.topGlow} />
      <div style={styles.bottomShade} />
    </AbsoluteFill>
  );
};

const styles: Record<string, React.CSSProperties> = {
  root: {
    backgroundColor: palette.bg,
    color: palette.text,
    fontFamily: '"IBM Plex Mono", "Cascadia Mono", Consolas, monospace',
    overflow: "hidden",
  },
  opening: {
    alignItems: "center",
    justifyContent: "flex-start",
    paddingTop: 72,
  },
  logoWrap: {
    height: 92,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  logo: {
    width: 470,
    height: "auto",
  },
  openingCopy: {
    textAlign: "center",
    width: 1180,
  },
  openingTitle: {
    margin: "22px 0 0",
    fontSize: 76,
    lineHeight: 1.02,
    fontWeight: 700,
    letterSpacing: 0,
  },
  openingDetail: {
    margin: "28px 0 0",
    fontSize: 28,
    lineHeight: 1.38,
    color: palette.muted,
  },
  heroScreenshot: {
    position: "absolute",
    left: 235,
    right: 235,
    bottom: -26,
    height: 520,
    border: `1px solid ${palette.border}`,
    borderRadius: 4,
    overflow: "hidden",
    boxShadow: "0 34px 90px rgba(0, 0, 0, 0.48)",
  },
  heroImage: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  scene: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 90,
    padding: "132px 120px 122px",
  },
  eyebrow: {
    color: palette.green,
    fontSize: 24,
    lineHeight: 1.2,
    textTransform: "uppercase",
    fontWeight: 700,
    marginBottom: 30,
  },
  sceneTitle: {
    fontSize: 64,
    lineHeight: 1.05,
    margin: 0,
    letterSpacing: 0,
  },
  sceneDetail: {
    fontSize: 27,
    lineHeight: 1.45,
    color: palette.muted,
    margin: "30px 0 0",
  },
  screenshotShell: {
    width: 1050,
    height: 646,
    border: `1px solid ${palette.border}`,
    borderRadius: 4,
    backgroundColor: palette.panel,
    boxShadow: "0 26px 72px rgba(0, 0, 0, 0.46)",
    overflow: "hidden",
  },
  windowBar: {
    height: 42,
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "0 18px",
    borderBottom: `1px solid ${palette.border}`,
    backgroundColor: palette.panel2,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 10,
    display: "inline-block",
  },
  windowLabel: {
    color: palette.muted,
    marginLeft: 12,
    fontSize: 15,
  },
  screenshotMask: {
    width: "100%",
    height: 604,
    overflow: "hidden",
  },
  closing: {
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    padding: "120px",
  },
  finalTitle: {
    width: 1160,
    margin: "36px 0 0",
    fontSize: 70,
    lineHeight: 1.08,
    letterSpacing: 0,
  },
  badges: {
    display: "flex",
    gap: 18,
    marginTop: 48,
  },
  badge: {
    display: "inline-flex",
    padding: "16px 20px",
    border: `1px solid ${palette.border}`,
    borderRadius: 4,
    backgroundColor: "rgba(40, 36, 35, 0.82)",
    color: palette.text,
    fontSize: 20,
  },
  repoLine: {
    margin: "52px 0 0",
    color: palette.green,
    fontSize: 26,
  },
  timelineWrap: {
    position: "absolute",
    left: 88,
    right: 88,
    bottom: 46,
    display: "flex",
    alignItems: "center",
    gap: 24,
  },
  timelineTrack: {
    flex: 1,
    height: 3,
    backgroundColor: "rgba(77, 70, 62, 0.72)",
  },
  timelineProgress: {
    height: "100%",
    backgroundColor: palette.green,
  },
  navDots: {
    display: "flex",
    gap: 10,
  },
  navDot: {
    width: 8,
    height: 8,
    borderRadius: 8,
    display: "inline-block",
  },
  topGlow: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: 250,
    background: "linear-gradient(180deg, rgba(127, 209, 155, 0.10), rgba(32, 29, 29, 0))",
  },
  bottomShade: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    height: 320,
    background: "linear-gradient(0deg, rgba(12, 10, 10, 0.52), rgba(32, 29, 29, 0))",
  },
};
