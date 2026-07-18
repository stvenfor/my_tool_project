import frozenData from './data/a-share-industry-flow-2026-07-17.json';
import {validateIndustryFlowData} from './schema';

export const industryFlowData = validateIndustryFlowData(frozenData);
