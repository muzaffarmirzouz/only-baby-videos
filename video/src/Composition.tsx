import {
  AbsoluteFill,
  Audio,
  CalculateMetadataFunction,
  Composition,
  Img,
  interpolate,
  Loop,
  OffthreadVideo,
  Sequence,
  Series,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont } from "@remotion/google-fonts/Fredoka";

// Mac'da ham, GitHub serverida (Linux) ham bir xil ko'rinishi uchun Google shrifti
const { fontFamily } = loadFont("normal", { weights: ["600", "700"], subsets: ["latin"] });

type Caption = { start: number; end: number; text: string };
// O'yin sahnasi: savol → taymer → javob (revealAt soniyada ochiladi)
type Quiz = {
  question: string;
  options: string[];
  answer: number;
  revealAt: number;
  countdown: number;
  answerAudio: string;
};
type Scene = {
  quiz?: Quiz | null;
  image: string;
  video: string | null;
  videoDuration: number | null;
  audio: string;
  duration: number;
  captions: Caption[];
  motion: number;
};
export type Props = {
  title: string;
  kind: string;
  vertical: boolean; // Shorts: 1080x1920
  music: string | null;
  musicVolume: number;
  scenes: Scene[];
};

const FPS = 30;
const introFrames = (vertical: boolean) => (vertical ? 45 : 90); // Shorts'da intro qisqa
const PAUSE_SECONDS = 0.5;
const COLORS = ["#ff5fa2", "#ffb800", "#38c9ff", "#7bdc4f", "#a970ff"];

const sceneFrames = (s: Scene) => Math.ceil((s.duration + PAUSE_SECONDS) * FPS);

const calculateMetadata: CalculateMetadataFunction<Props> = ({ props }) => {
  const total = props.scenes.reduce((sum, s) => sum + sceneFrames(s), introFrames(props.vertical));
  return {
    durationInFrames: Math.max(total, 1),
    width: props.vertical ? 1080 : 1920,
    height: props.vertical ? 1920 : 1080,
  };
};

const defaultProps: Props = { title: "My Kids Video", kind: "story", vertical: false, music: null, musicVolume: 0.12, scenes: [] };

export const MyComposition = () => {
  return (
    <Composition
      id="KidsVideo"
      component={KidsVideo}
      durationInFrames={90}
      fps={FPS}
      width={1920}
      height={1080}
      defaultProps={defaultProps}
      calculateMetadata={calculateMetadata}
    />
  );
};

export const KidsVideo: React.FC<Props> = ({ title, kind, vertical, music, musicVolume, scenes }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#fff4d6" }}>
      {music ? <Audio src={staticFile(music)} volume={musicVolume} loop /> : null}
      <Series>
        <Series.Sequence durationInFrames={introFrames(vertical)}>
          <Intro title={title.replace(/\s*#shorts/i, "")} image={scenes[0]?.image} vertical={vertical} />
        </Series.Sequence>
        {scenes.map((s, i) => (
          <Series.Sequence key={i} durationInFrames={sceneFrames(s)}>
            {s.quiz ? (
              <QuizScene scene={s} quiz={s.quiz} vertical={vertical} />
            ) : (
              <SceneView scene={s} index={i} cartoon={kind === "cartoon"} vertical={vertical} />
            )}
          </Series.Sequence>
        ))}
      </Series>
    </AbsoluteFill>
  );
};

const Intro: React.FC<{ title: string; image?: string; vertical: boolean }> = ({ title, image, vertical }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const { fps } = useVideoConfig();
  const words = title.split(" ");
  const fadeOut = interpolate(frame, [durationInFrames - 12, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ opacity: fadeOut }}>
      {image ? (
        <Img src={staticFile(image)} style={{ width: "100%", height: "100%", objectFit: "cover", filter: "blur(8px) brightness(0.9)" }} />
      ) : null}
      <AbsoluteFill style={{ justifyContent: "center", alignContent: "center", alignItems: "center", padding: vertical ? 70 : 120, flexWrap: "wrap", flexDirection: "row", gap: 28 }}>
        {words.map((w, i) => {
          const pop = spring({ frame: frame - i * 4, fps, config: { damping: 9, mass: 0.6 } });
          return (
            <span
              key={i}
              style={{
                fontFamily: fontFamily,
                fontSize: vertical ? 130 : 120,
                fontWeight: 700,
                color: COLORS[i % COLORS.length],
                WebkitTextStroke: "6px #1e1e5a",
                paintOrder: "stroke fill",
                transform: `scale(${pop}) rotate(${(i % 2 ? 1 : -1) * 4 * (1 - pop)}deg)`,
                display: "inline-block",
              }}
            >
              {w}
            </span>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const SceneView: React.FC<{ scene: Scene; index: number; cartoon: boolean; vertical: boolean }> = ({ scene, cartoon, vertical }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const p = frame / durationInFrames;
  // Multik: sahna "sakrab" kiradi va sekin chayqaladi
  const enter = cartoon ? spring({ frame, fps, config: { damping: 8, mass: 0.7 } }) : 1;
  const wobble = cartoon ? Math.sin(frame / 18) * 1.2 : 0;
  const bob = cartoon ? Math.sin(frame / 11) * 0.6 : 0;

  // Ken Burns harakati: yaqinlashish, uzoqlashish, o'ngga va chapga surilish
  const motions = [
    { scale: 1 + 0.15 * p, x: 0 },
    { scale: 1.15 - 0.15 * p, x: 0 },
    { scale: 1.15, x: -6 + 12 * p },
    { scale: 1.15, x: 6 - 12 * p },
  ];
  const m = motions[scene.motion % motions.length];
  const opacity = interpolate(frame, [0, 10, durationInFrames - 10, durationInFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const t = frame / fps;
  const caption = scene.captions.find((c) => t >= c.start && t < c.end);
  const capStart = caption ? Math.round(caption.start * fps) : 0;
  const pop = spring({ frame: frame - capStart, fps, config: { damping: 12 } });

  return (
    <AbsoluteFill style={{ opacity }}>
      <AbsoluteFill style={{ overflow: "hidden" }}>
        {scene.video && scene.videoDuration ? (
          // Pixabay klipi: sahnadan qisqa bo'lsa takrorlanadi, o'z ovozi o'chirilgan
          <Loop durationInFrames={Math.max(1, Math.floor(scene.videoDuration * fps) - 1)}>
            <OffthreadVideo
              src={staticFile(scene.video)}
              muted
              style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${1 + 0.05 * p})` }}
            />
          </Loop>
        ) : (
          <Img
            src={staticFile(scene.image)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              transform: `scale(${m.scale * (0.85 + 0.15 * enter)}) translateX(${m.x}%) translateY(${bob}%) rotate(${wobble}deg)`,
            }}
          />
        )}
      </AbsoluteFill>
      <Audio src={staticFile(scene.audio)} />
      {caption ? (
        <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: vertical ? 380 : 60 }}>
          <div
            style={{
              maxWidth: vertical ? 940 : 1500,
              padding: "22px 44px",
              borderRadius: 36,
              backgroundColor: "rgba(20, 20, 60, 0.62)",
              color: "white",
              fontFamily: fontFamily,
              fontSize: vertical ? 74 : 60,
              lineHeight: 1.25,
              textAlign: "center",
              transform: `scale(${0.85 + 0.15 * pop})`,
            }}
          >
            {caption.text}
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};

const OPTION_COLORS = ["#ff5fa2", "#38c9ff", "#ffb800"];

const QuizScene: React.FC<{ scene: Scene; quiz: Quiz; vertical: boolean }> = ({ scene, quiz, vertical }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const t = frame / fps;
  const revealFrame = Math.round(quiz.revealAt * fps);
  const revealed = frame >= revealFrame;
  const reveal = spring({ frame: frame - revealFrame, fps, config: { damping: 10 } });
  const countStart = quiz.revealAt - quiz.countdown;
  const left = Math.ceil(quiz.revealAt - t);
  const opacity = interpolate(frame, [0, 10, durationInFrames - 10, durationInFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const caption = revealed ? scene.captions.find((c) => t >= c.start && t < c.end) : undefined;

  return (
    <AbsoluteFill style={{ opacity, fontFamily }}>
      {/* Javob ochilguncha rasm yashirin (xira) */}
      <Img
        src={staticFile(scene.image)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          filter: `blur(${revealed ? 28 * (1 - reveal) : 28}px) brightness(${revealed ? 0.6 + 0.4 * reveal : 0.6})`,
          transform: `scale(${1.1 - 0.05 * (revealed ? reveal : 0)})`,
        }}
      />
      <Audio src={staticFile(scene.audio)} />
      <Sequence from={revealFrame}>
        <Audio src={staticFile(quiz.answerAudio)} />
      </Sequence>

      <AbsoluteFill style={{ alignItems: "center", paddingTop: vertical ? 240 : 70 }}>
        <div
          style={{
            fontSize: vertical ? 92 : 84,
            fontWeight: 700,
            color: "#fff",
            textAlign: "center",
            maxWidth: vertical ? 960 : 1600,
            WebkitTextStroke: "5px #1e1e5a",
            paintOrder: "stroke fill",
            transform: `scale(${spring({ frame, fps, config: { damping: 9 } })})`,
          }}
        >
          {quiz.question}
        </div>
      </AbsoluteFill>

      <AbsoluteFill
        style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: vertical ? (caption ? 560 : 420) : caption ? 230 : 110 }}
      >
        <div style={{ display: "flex", flexDirection: vertical ? "column" : "row", gap: vertical ? 28 : 40 }}>
          {quiz.options.map((o, i) => {
            const pop = spring({ frame: frame - 8 - i * 6, fps, config: { damping: 9, mass: 0.6 } });
            const correct = i === quiz.answer;
            const bg = revealed ? (correct ? "#2fbf71" : "rgba(40,40,70,0.75)") : OPTION_COLORS[i % 3];
            const scale = pop * (revealed ? (correct ? 1 + 0.12 * reveal : 0.9) : 1);
            return (
              <div
                key={i}
                style={{
                  minWidth: vertical ? 760 : 380,
                  padding: "26px 40px",
                  borderRadius: 36,
                  background: bg,
                  color: "#fff",
                  fontSize: 64,
                  fontWeight: 700,
                  textAlign: "center",
                  boxShadow: "0 12px 0 rgba(0,0,0,0.25)",
                  opacity: revealed && !correct ? 0.6 : 1,
                  transform: `scale(${scale})`,
                }}
              >
                {String.fromCharCode(65 + i)}. {o}
                {revealed && correct ? " ✓" : ""}
              </div>
            );
          })}
        </div>
      </AbsoluteFill>

      {/* Taymer */}
      {t >= countStart && !revealed ? (
        <AbsoluteFill style={{ justifyContent: vertical ? "flex-start" : "center", alignItems: "center", paddingTop: vertical ? 560 : 0 }}>
          <div
            style={{
              width: 260,
              height: 260,
              borderRadius: "50%",
              background: "#ffb800",
              border: "14px solid #fff",
              display: "grid",
              placeItems: "center",
              fontSize: 150,
              fontWeight: 700,
              color: "#1e1e5a",
              transform: `scale(${1 + 0.12 * Math.max(0, 1 - ((t - countStart) % 1) * 4)})`,
              boxShadow: "0 16px 40px rgba(0,0,0,0.35)",
            }}
          >
            {left}
          </div>
        </AbsoluteFill>
      ) : null}

      {caption ? (
        <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: vertical ? 300 : 60 }}>
          <div
            style={{
              maxWidth: vertical ? 940 : 1500,
              padding: "18px 40px",
              borderRadius: 32,
              backgroundColor: "rgba(20, 20, 60, 0.7)",
              color: "white",
              fontSize: 52,
              textAlign: "center",
            }}
          >
            {caption.text}
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
