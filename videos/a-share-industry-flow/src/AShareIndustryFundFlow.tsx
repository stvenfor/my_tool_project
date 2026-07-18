import {AbsoluteFill, Sequence} from 'remotion';
import type {IndustryFlowData} from './schema';
import {Background} from './components/Background';
import {FlowScene} from './scenes/FlowScene';
import {OutroScene} from './scenes/OutroScene';
import {TitleScene} from './scenes/TitleScene';

export const AShareIndustryFundFlow = (props: IndustryFlowData) => {
  return (
    <AbsoluteFill>
      <Background>
        <Sequence from={0} durationInFrames={38} premountFor={12}>
          <TitleScene />
        </Sequence>
        <Sequence from={30} durationInFrames={116} premountFor={12}>
          <FlowScene items={props.inflowTop5} direction="inflow" sceneDuration={116} />
        </Sequence>
        <Sequence from={142} durationInFrames={118} premountFor={12}>
          <FlowScene items={props.outflowTop5} direction="outflow" sceneDuration={118} />
        </Sequence>
        <Sequence from={256} durationInFrames={59} premountFor={12}>
          <OutroScene />
        </Sequence>
      </Background>
    </AbsoluteFill>
  );
};
