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
// Multik qahramoni: fonsiz PNG, Remotion'da harakatlantiriladi
type Puppet = { src: string; position: "left" | "center" | "right"; action: string; speaking: boolean };
type Scene = {
  quiz?: Quiz | null;
  puppets?: Puppet[];
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
  const hasPuppets = Boolean(scene.puppets?.length);
  const playful = cartoon && !hasPuppets; // qahramonlar bo'lsa fon tinch turadi
  const enter = playful ? spring({ frame, fps, config: { damping: 8, mass: 0.7 } }) : 1;
  const wobble = playful ? Math.sin(frame / 18) * 1.2 : 0;
  const bob = playful ? Math.sin(frame / 11) * 0.6 : 0;

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
      {/* o'rtadagi qahramon orqada (birinchi chiziladi), chetdagilar oldinda */}
      {[...(scene.puppets ?? []).map((pp, k) => ({ pp, k }))]
        .sort((a, b) => Number(b.pp.position === "center") - Number(a.pp.position === "center"))
        .map(({ pp, k }) => (
          <PuppetView key={k} puppet={pp} index={k} count={scene.puppets!.length} vertical={vertical} />
        ))}
      <Audio src={staticFile(scene.audio)} />
      {caption ? (
        <AbsoluteFill
          style={{
            // Qahramonlar bo'lsa subtitr ularning yuzini to'smasin: tikda tepasida, gorizontalda yuqorida
            justifyContent: hasPuppets && !vertical ? "flex-start" : "flex-end",
            alignItems: "center",
            paddingTop: hasPuppets && !vertical ? 50 : 0,
            paddingBottom: vertical ? (hasPuppets ? 960 : 380) : 60,
          }}
        >
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

const POS_X = { left: 0.25, center: 0.5, right: 0.75 };

const PuppetView: React.FC<{ puppet: Puppet; index: number; count: number; vertical: boolean }> = ({
  puppet,
  index,
  count,
  vertical,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const t = frame / fps;
  const delay = index * 6; // qahramonlar ketma-ket chiqadi
  const f = Math.max(0, frame - delay);
  // Tik ekranda qahramonlar ko'p bo'lsa kichikroq va chetroqda — bir-birini to'smasin
  const center = puppet.position === "center";
  const crowd = vertical ? (count >= 3 ? 0.33 : count === 2 ? 0.38 : 0.42) : count >= 3 ? 0.56 : 0.62;
  const h = height * crowd * (center && count >= 3 ? 0.9 : 1);
  const spread = vertical && count >= 2 ? { left: 0.2, center: 0.5, right: 0.8 } : POS_X;
  const baseX = width * spread[puppet.position];
  const faceLeft = puppet.position === "right"; // o'ngdagilar markazga qaraydi
  const pop = spring({ frame: f, fps, config: { damping: 10, mass: 0.6 } });
  const seed = index * 1.7;

  let x = baseX;
  let y = 0; // yuqoriga (px)
  let rot = 0;
  let sx = 1;
  let sy = 1;
  let flip = faceLeft ? -1 : 1;
  let scale = pop;

  switch (puppet.action) {
    case "walk_in":
    case "run_across": {
      const across = puppet.action === "run_across";
      const fromLeft = puppet.position !== "right";
      const start = fromLeft ? -width * 0.2 : width * 1.2;
      const end = across ? (fromLeft ? width * 1.2 : -width * 0.2) : baseX;
      const dur = across ? durationInFrames * 0.9 : fps * 1.4;
      const k = interpolate(f, [0, dur], [0, 1], { extrapolateRight: "clamp" });
      const walking = k < 1;
      x = start + (end - start) * (across ? k : 1 - Math.pow(1 - k, 2));
      y = walking ? Math.abs(Math.sin(t * (across ? 14 : 10))) * h * 0.05 : 0;
      rot = walking ? Math.sin(t * (across ? 14 : 10)) * 4 : 0;
      flip = fromLeft ? 1 : -1;
      scale = 1;
      break;
    }
    case "hop": {
      const ph = Math.abs(Math.sin(t * 4 + seed));
      y = ph * h * 0.12;
      sy = 1 + (ph < 0.15 ? -0.08 : 0.03); // yerga tushganda siqiladi
      sx = 2 - sy;
      break;
    }
    case "wave":
      rot = Math.sin(t * 6 + seed) * 7;
      break;
    case "spin":
      flip *= Math.cos(t * 3 + seed) >= 0 ? 1 : -1;
      sx = Math.max(0.15, Math.abs(Math.cos(t * 3 + seed)));
      break;
    case "peek": {
      const k = spring({ frame: f, fps, config: { damping: 14 } });
      y = -h * 0.55 * (1 - k) + Math.sin(t * 2 + seed) * h * 0.02;
      scale = 1;
      break;
    }
    case "bounce":
      sy = 1 + Math.sin(t * 5 + seed) * 0.05;
      sx = 1 - Math.sin(t * 5 + seed) * 0.03;
      y = Math.max(0, Math.sin(t * 5 + seed)) * h * 0.04;
      break;
    default: // idle: nafas olish
      sy = 1 + Math.sin(t * 2 + seed) * 0.015;
  }

  if (puppet.speaking) {
    // gapirayotgan qahramon biroz tebranadi
    sy *= 1 + Math.abs(Math.sin(t * 11)) * 0.035;
    rot += Math.sin(t * 7) * 1.5;
  }

  const groundY = height * (center && count >= 3 ? 0.93 : 0.97); // o'rtadagi biroz orqada
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* soya */}
      <div
        style={{
          position: "absolute",
          left: x - h * 0.22,
          top: groundY - h * 0.03,
          width: h * 0.44,
          height: h * 0.06,
          borderRadius: "50%",
          background: "rgba(0,0,0,0.22)",
          transform: `scale(${Math.max(0.5, 1 - y / h)})`,
          opacity: scale,
        }}
      />
      <Img
        src={staticFile(puppet.src)}
        style={{
          position: "absolute",
          height: h,
          left: x,
          top: groundY - h - y,
          transform: `translateX(-50%) rotate(${rot}deg) scale(${scale * sx * flip}, ${scale * sy})`,
          transformOrigin: "50% 100%",
          filter: "drop-shadow(0 6px 10px rgba(0,0,0,0.25))",
        }}
      />
    </AbsoluteFill>
  );
};
