#!/usr/bin/env python3
"""Generate 10x CET-4/6 daily vocab markdown (80 words + 40 phrases/day)."""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).with_name("daily-vocab-30day.md")

# Each day: title, roots (list of (name, meaning, examples_md_rows)),
# words: list of (word, ipa, gloss, tip), phrases: list of (phrase, ipa, gloss, example)

Day = dict


def W(word: str, ipa: str, gloss: str, tip: str = "") -> tuple:
    return (word, ipa, gloss, tip or "—")


def P(phrase: str, ipa: str, gloss: str, ex: str) -> tuple:
    return (phrase, ipa, gloss, ex)


DAYS: list[Day] = []


def add_day(
    n: int,
    title: str,
    roots: list[tuple[str, str, list[tuple[str, str]]]],
    words: list[tuple],
    phrases: list[tuple],
) -> None:
    assert len(words) == 80, f"Day {n}: {len(words)} words"
    assert len(phrases) == 40, f"Day {n}: {len(phrases)} phrases"
    DAYS.append(
        {
            "n": n,
            "title": title,
            "roots": roots,
            "words": words,
            "phrases": phrases,
        }
    )


# ---------- Day 1 cogn/sci ----------
add_day(
    1,
    "认知与学习 | cogn / sci / prehend / ceiv = 知·抓·取",
    [
        (
            "cogn / sci / prehend / ceiv",
            "知道 / 抓住 / 取",
            [
                ("cogn", "recognize, cognitive, cognition, incognito"),
                ("sci", "science, conscious, conscience, omniscient"),
                ("prehend / prehens", "comprehend, apprehend, comprehensive"),
                ("ceiv / cept", "perceive, receive, concept, deceive"),
            ],
        )
    ],
    [
        W("acquire", "/əˈkwaɪər/", "v. 获得；习得", "ac- + quire"),
        W("cognitive", "/ˈkɑːɡnətɪv/", "a. 认知的", "cogn"),
        W("comprehend", "/ˌkɑːmprɪˈhend/", "v. 理解", "com- + prehend"),
        W("conscious", "/ˈkɑːnʃəs/", "a. 有意识的", "sci"),
        W("perceive", "/pərˈsiːv/", "v. 察觉；认为", "per- + ceive"),
        W("retain", "/rɪˈteɪn/", "v. 保留；记住", "re- + tain"),
        W("assimilate", "/əˈsɪməleɪt/", "v. 吸收；同化", "simil"),
        W("insight", "/ˈɪnsaɪt/", "n. 洞察", "in + sight"),
        W("cognition", "/kɑːɡˈnɪʃn/", "n. 认知", "cogn + -ion"),
        W("recognition", "/ˌrekəɡˈnɪʃn/", "n. 认出；承认", "re- + cogn"),
        W("recognize", "/ˈrekəɡnaɪz/", "v. 认出；承认", "re- + cogn"),
        W("acknowledge", "/əkˈnɑːlɪdʒ/", "v. 承认；致谢", "knowledge"),
        W("apprehend", "/ˌæprɪˈhend/", "v. 忧虑；逮捕；理解", "ap- + prehend"),
        W("apprehension", "/ˌæprɪˈhenʃn/", "n. 忧虑；理解", "apprehend"),
        W("comprehensive", "/ˌkɑːmprɪˈhensɪv/", "a. 全面的", "comprehend"),
        W("comprehension", "/ˌkɑːmprɪˈhenʃn/", "n. 理解力", "comprehend"),
        W("conceive", "/kənˈsiːv/", "v. 构想；怀孕", "con- + ceive"),
        W("concept", "/ˈkɑːnsept/", "n. 概念", "cept"),
        W("conception", "/kənˈsepʃn/", "n. 概念；构想", "concept"),
        W("deceive", "/dɪˈsiːv/", "v. 欺骗", "de- + ceive"),
        W("deception", "/dɪˈsepʃn/", "n. 欺骗", "deceive"),
        W("perceive", "/pərˈsiːv/", "v. 感知（复现）", "复现巩固"),
        W("perception", "/pərˈsepʃn/", "n. 感知；看法", "perceive"),
        W("perceptive", "/pərˈseptɪv/", "a. 敏锐的", "perceive"),
        W("receive", "/rɪˈsiːv/", "v. 接收", "re- + ceive"),
        W("reception", "/rɪˈsepʃn/", "n. 接待；接收", "receive"),
        W("receptive", "/rɪˈseptɪv/", "a. 乐于接受的", "receive"),
        W("science", "/ˈsaɪəns/", "n. 科学", "sci"),
        W("scientific", "/ˌsaɪənˈtɪfɪk/", "a. 科学的", "science"),
        W("conscience", "/ˈkɑːnʃəns/", "n. 良心", "con- + sci"),
        W("conscientious", "/ˌkɑːnʃiˈenʃəs/", "a. 认真的；凭良心的", "conscience"),
        W("unconscious", "/ʌnˈkɑːnʃəs/", "a. 无意识的", "un- + conscious"),
        W("subconscious", "/ˌsʌbˈkɑːnʃəs/", "a./n. 潜意识（的）", "sub-"),
        W("omniscient", "/ɑːmˈnɪʃənt/", "a. 全知的", "omni- + sci"),
        W("memorize", "/ˈmeməraɪz/", "v. 记住", "memory"),
        W("memory", "/ˈmeməri/", "n. 记忆", "memor"),
        W("memorable", "/ˈmemərəbl/", "a. 难忘的", "memory"),
        W("remind", "/rɪˈmaɪnd/", "v. 提醒", "re- + mind"),
        W("reminder", "/rɪˈmaɪndər/", "n. 提醒物", "remind"),
        W("recollect", "/ˌrekəˈlekt/", "v. 回忆", "re- + collect"),
        W("recollection", "/ˌrekəˈlekʃn/", "n. 回忆", "recollect"),
        W("recall", "/rɪˈkɔːl/", "v. 回想；召回", "re- + call"),
        W("retain", "/rɪˈteɪn/", "v. 保持（复现）", "tain"),
        W("retention", "/rɪˈtenʃn/", "n. 保持；记忆力", "retain"),
        W("learn", "/lɜːrn/", "v. 学习", "基础强化"),
        W("learning", "/ˈlɜːrnɪŋ/", "n. 学习", "learn"),
        W("learner", "/ˈlɜːrnər/", "n. 学习者", "learn"),
        W("instruct", "/ɪnˈstrʌkt/", "v. 指导", "in- + struct"),
        W("instruction", "/ɪnˈstrʌkʃn/", "n. 指示；教学", "instruct"),
        W("instructive", "/ɪnˈstrʌktɪv/", "a. 有启发的", "instruct"),
        W("educate", "/ˈedʒukeɪt/", "v. 教育", "e- + duc"),
        W("education", "/ˌedʒuˈkeɪʃn/", "n. 教育", "educate"),
        W("educational", "/ˌedʒuˈkeɪʃənl/", "a. 教育的", "education"),
        W("literacy", "/ˈlɪtərəsi/", "n. 读写能力", "liter"),
        W("literate", "/ˈlɪtərət/", "a. 有读写能力的", "liter"),
        W("illiterate", "/ɪˈlɪtərət/", "a. 文盲的", "il- + literate"),
        W("curriculum", "/kəˈrɪkjələm/", "n. 课程（体系）", "四六级"),
        W("discipline", "/ˈdɪsəplɪn/", "n. 学科；纪律", "四六级"),
        W("academic", "/ˌækəˈdemɪk/", "a. 学术的", "academy"),
        W("scholarship", "/ˈskɑːlərʃɪp/", "n. 学问；奖学金", "scholar"),
        W("scholar", "/ˈskɑːlər/", "n. 学者", "school 同源"),
        W("tuition", "/tuˈɪʃn/", "n. 学费；讲授", "四六级"),
        W("tutorial", "/tuːˈtɔːriəl/", "n. 辅导课；a. 辅导的", "tutor"),
        W("mentor", "/ˈmentɔːr/", "n. 导师", "六级"),
        W("expertise", "/ˌekspɜːrˈtiːz/", "n. 专长", "expert"),
        W("proficient", "/prəˈfɪʃnt/", "a. 熟练的", "pro- + fic"),
        W("proficiency", "/prəˈfɪʃnsi/", "n. 熟练", "proficient"),
        W("fluent", "/ˈfluːənt/", "a. 流利的", "flu"),
        W("fluency", "/ˈfluːənsi/", "n. 流利", "fluent"),
        W("articulate", "/ɑːrˈtɪkjuleɪt/", "v. 清晰表达；a. 口齿清楚的", "六级"),
        W("elaborate", "/ɪˈlæbəreɪt/", "v. 详述；a. 详尽的", "e- + labor"),
        W("clarify", "/ˈklærɪfaɪ/", "v. 澄清", "clar + -ify"),
        W("clarity", "/ˈklærəti/", "n. 清晰", "clear"),
        W("interpret", "/ɪnˈtɜːrprɪt/", "v. 解释；口译", "inter-"),
        W("interpretation", "/ɪnˌtɜːrprɪˈteɪʃn/", "n. 解释", "interpret"),
        W("analyze", "/ˈænəlaɪz/", "v. 分析", "ana- + lyze"),
        W("analysis", "/əˈnæləsɪs/", "n. 分析（pl. analyses）", "analyze"),
        W("analytical", "/ˌænəˈlɪtɪkl/", "a. 分析的", "analysis"),
        W("synthesize", "/ˈsɪnθəsaɪz/", "v. 综合；合成", "syn + thes"),
        W("synthesis", "/ˈsɪnθəsɪs/", "n. 综合", "synthesize"),
        W("hypothesis", "/haɪˈpɑːθəsɪs/", "n. 假设", "hypo + thesis"),
        W("theory", "/ˈθɪri/", "n. 理论", "theoretical"),
        W("theoretical", "/ˌθiːəˈretɪkl/", "a. 理论的", "theory"),
    ],
    [
        P("acquire a skill", "/əˈkwaɪər ə skɪl/", "掌握技能", "Acquire a skill in coding."),
        P("be conscious of", "/bi ˈkɑːnʃəs əv/", "意识到", "Be conscious of bias."),
        P("gain insight into", "/ɡeɪn ˈɪnsaɪt ˈɪntuː/", "深入了解", "Gain insight into memory."),
        P("beyond comprehension", "/bɪˈjɑːnd ˌkɑːmprɪˈhenʃn/", "无法理解", "Beyond comprehension."),
        P("cognitive ability", "/ˈkɑːɡnətɪv əˈbɪləti/", "认知能力", "Cognitive ability matters."),
        P("in recognition of", "/ɪn ˌrekəɡˈnɪʃn əv/", "为表彰", "In recognition of his work."),
        P("acknowledge the fact", "/əkˈnɑːlɪdʒ ðə fækt/", "承认事实", "Acknowledge the fact."),
        P("comprehensive review", "/ˌkɑːmprɪˈhensɪv rɪˈvjuː/", "全面复习", "A comprehensive review."),
        P("common misconception", "/ˈkɑːmən ˌmɪsənˈsepʃn/", "常见误解", "A common misconception."),
        P("from my perspective", "/frəm maɪ pərˈspektɪv/", "依我看", "From my perspective."),
        P("retain information", "/rɪˈteɪn ˌɪnfərˈmeɪʃn/", "记住信息", "Retain information longer."),
        P("long-term memory", "/ˌlɔːŋ ˈtɜːrm ˈmeməri/", "长期记忆", "Long-term memory."),
        P("remind sb of", "/rɪˈmaɪnd ˈsʌmbədi əv/", "使想起", "Remind me of home."),
        P("academic performance", "/ˌækəˈdemɪk pərˈfɔːrməns/", "学业表现", "Improve academic performance."),
        P("higher education", "/ˈhaɪər ˌedʒuˈkeɪʃn/", "高等教育", "Higher education."),
        P("curriculum design", "/kəˈrɪkjələm dɪˈzaɪn/", "课程设计", "Curriculum design."),
        P("literacy rate", "/ˈlɪtərəsi reɪt/", "识字率", "Literacy rate rose."),
        P("be proficient in", "/bi prəˈfɪʃnt ɪn/", "精通", "Proficient in English."),
        P("fluent in", "/ˈfluːənt ɪn/", "流利使用", "Fluent in Mandarin."),
        P("clarify a point", "/ˈklærɪfaɪ ə pɔɪnt/", "澄清一点", "Clarify a point."),
        P("interpret the data", "/ɪnˈtɜːrprɪt ðə ˈdeɪtə/", "解读数据", "Interpret the data."),
        P("analyze the results", "/ˈænəlaɪz ðə rɪˈzʌlts/", "分析结果", "Analyze the results."),
        P("test a hypothesis", "/test ə haɪˈpɑːθəsɪs/", "检验假设", "Test a hypothesis."),
        P("in theory", "/ɪn ˈθɪri/", "理论上", "In theory, it works."),
        P("theoretical framework", "/ˌθiːəˈretɪkl ˈfreɪmwɜːrk/", "理论框架", "A theoretical framework."),
        P("assimilate knowledge", "/əˈsɪməleɪt ˈnɑːlɪdʒ/", "吸收知识", "Assimilate knowledge."),
        P("deep learning", "/diːp ˈlɜːrnɪŋ/", "深度学习（亦指 artificial）", "Deep learning methods."),
        P("learning curve", "/ˈlɜːrnɪŋ kɜːrv/", "学习曲线", "A steep learning curve."),
        P("instructional design", "/ɪnˈstrʌkʃənl dɪˈzaɪn/", "教学设计", "Instructional design."),
        P("follow instructions", "/ˈfɑːloʊ ɪnˈstrʌkʃnz/", "遵循说明", "Follow instructions."),
        P("expertise in", "/ˌekspɜːrˈtiːz ɪn/", "在…方面的专长", "Expertise in finance."),
        P("mentor a student", "/ˈmentɔːr ə ˈstuːdnt/", "指导学生", "Mentor a student."),
        P("pay tuition", "/peɪ tuˈɪʃn/", "交学费", "Pay tuition fees."),
        P("scholarship program", "/ˈskɑːlərʃɪp ˈproʊɡræm/", "奖学金项目", "A scholarship program."),
        P("critical thinking", "/ˈkrɪtɪkl ˈθɪŋkɪŋ/", "批判性思维", "Critical thinking skills."),
        P("knowledge retention", "/ˈnɑːlɪdʒ rɪˈtenʃn/", "知识保持", "Knowledge retention."),
        P("subconscious mind", "/ˌsʌbˈkɑːnʃəs maɪnd/", "潜意识", "The subconscious mind."),
        P("clear conscience", "/klɪr ˈkɑːnʃəns/", "问心无愧", "With a clear conscience."),
        P("conscientious student", "/ˌkɑːnʃiˈenʃəs ˈstuːdnt/", "勤奋认真的学生", "A conscientious student."),
        P("elaborate on", "/ɪˈlæbəreɪt ɑːn/", "详述", "Elaborate on your idea."),
    ],
)

print(f"Day1 words={len(DAYS[0]['words'])} phrases={len(DAYS[0]['phrases'])}")
# Day1 has duplicate perceive and retain - need exactly 80 unique-ish entries
# Count: I may have more than 80. Let me check and fix in a more scalable way.
