import {Composition} from 'remotion';
import {AShareIndustryFundFlow} from './AShareIndustryFundFlow';
import {industryFlowData} from './data';
import {industryFlowDataSchema} from './schema';

export const RemotionRoot = () => {
  return (
    <Composition
      id="AShareIndustryFundFlow"
      component={AShareIndustryFundFlow}
      durationInFrames={315}
      fps={30}
      width={1080}
      height={1920}
      schema={industryFlowDataSchema}
      defaultProps={industryFlowData}
    />
  );
};
