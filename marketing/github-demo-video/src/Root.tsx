import { Composition } from "remotion";
import { FarmTrackGithubDemo } from "./FarmTrackGithubDemo";

export const RemotionRoot = () => {
  return (
    <Composition
      id="FarmTrackGithubDemo"
      component={FarmTrackGithubDemo}
      durationInFrames={900}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
