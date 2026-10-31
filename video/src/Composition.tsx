import {
  AbsoluteFill,
  Audio,
  CalculateMetadataFunction,
  Composition,
  Img,
  interpolate,
  Loop,
  OffthreadVideo,
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
type Scene = {
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
  music: string | null;
  musicVolume: number;
  scenes: Scene[];
};

const FPS = 30;
const INTRO_SECONDS = 3;
const PAUSE_SECONDS = 0.5;
const COLORS = ["#ff5fa2", "#ffb800", "#38c9ff", "#7bdc4f", "#a970ff"];

const sceneFrames = (s: Scene) => Math.ceil((s.duration + PAUSE_SECONDS) * FPS);

const calculateMetadata: CalculateMetadataFunction<Props> = ({ props }) => {
  const total = props.scenes.reduce((sum, s) => sum + sceneFrames(s), INTRO_SECONDS * FPS);
  return { durationInFrames: Math.max(total, 1) };
};

const defaultProps: Props = { title: "My Kids Video", music: null, musicVolume: 0.12, scenes: [] };

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

export const KidsVideo: React.FC<Props> = ({ title, music, musicVolume, scenes }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#fff4d6" }}>
      {music ? <Audio src={staticFile(music)} volume={musicVolume} loop /> : null}
      <Series>
        <Series.Sequence durationInFrames={INTRO_SECONDS * FPS}>
          <Intro title={title} image={scenes[0]?.image} />
        </Series.Sequence>
        {scenes.map((s, i) => (
          <Series.Sequence key={i} durationInFrames={sceneFrames(s)}>
            <SceneView scene={s} index={i} />
          </Series.Sequence>
        ))}
      </Series>
    </AbsoluteFill>
  );
};

const Intro: React.FC<{ title: string; image?: string }> = ({ title, image }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = title.split(" ");
  const fadeOut = interpolate(frame, [INTRO_SECONDS * fps - 12, INTRO_SECONDS * fps], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ opacity: fadeOut }}>
      {image ? (
        <Img src={staticFile(image)} style={{ width: "100%", height: "100%", objectFit: "cover", filter: "blur(8px) brightness(0.9)" }} />
      ) : null}
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: 120, flexWrap: "wrap", flexDirection: "row", gap: 28 }}>
        {words.map((w, i) => {
          const pop = spring({ frame: frame - i * 4, fps, config: { damping: 9, mass: 0.6 } });
          return (
            <span
              key={i}
              style={{
                fontFamily: fontFamily,
                fontSize: 120,
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

const SceneView: React.FC<{ scene: Scene; index: number }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const p = frame / durationInFrames;

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
            style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${m.scale}) translateX(${m.x}%)` }}
          />
        )}
      </AbsoluteFill>
      <Audio src={staticFile(scene.audio)} />
      {caption ? (
        <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 60 }}>
          <div
            style={{
              maxWidth: 1500,
              padding: "22px 44px",
              borderRadius: 36,
              backgroundColor: "rgba(20, 20, 60, 0.62)",
              color: "white",
              fontFamily: fontFamily,
              fontSize: 60,
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
