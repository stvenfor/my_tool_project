import { useVideoConfig } from "remotion";

export const useVideoLayout = () => {
  const { width, height } = useVideoConfig();
  const isLandscape = width > height;

  return {
    isLandscape,
    width,
    height,
    headerHeight: isLandscape ? 76 : 118,
    headlineSize: isLandscape ? 40 : 50,
    seriesTitleSize: isLandscape ? 24 : 28,
    philosophySize: isLandscape ? 20 : 24,
    subtitleSize: isLandscape ? 28 : 34,
    endCardTitleSize: isLandscape ? 30 : 36,
    endCardLabelSize: isLandscape ? 18 : 22,
  };
};
