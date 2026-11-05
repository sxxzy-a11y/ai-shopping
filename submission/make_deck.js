const pptxgen = require("pptxgenjs");
const path = require("path");

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "智购参谋";
pptx.subject = "全国人工智能应用创新大赛参赛作品";
pptx.title = "智购参谋：把推荐理由摊开";
pptx.company = "智购参谋";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};

const C = {
  ink: "171511",
  ink2: "2A241D",
  cream: "F5F3EE",
  paper: "FFFEFA",
  amber: "D3923C",
  gold: "E7C27A",
  brown: "3B3328",
  muted: "75685A",
  line: "E4D9C8",
  green: "4F7A5E",
  red: "A14B3D",
};
const W = 13.333;
const H = 7.5;
const M = 0.66;
const SHOTS = path.resolve("submission/screenshots");

function bg(slide, color = C.cream) {
  slide.background = { color };
}
function kicker(slide, text, color = C.amber, y = 0.62) {
  slide.addText(text, {
    x: M, y, w: 8.5, h: 0.28,
    fontFace: "Microsoft YaHei", fontSize: 10.5, bold: true,
    color, charSpacing: 1.6, margin: 0,
  });
}
function title(slide, text, color = C.ink, y = 0.95, size = 31) {
  slide.addText(text, {
    x: M, y, w: 11.9, h: 0.62,
    fontFace: "Microsoft YaHei", fontSize: size, bold: true,
    color, margin: 0, fit: "shrink",
  });
}
function subtitle(slide, text, color = C.muted, y = 1.62, w = 11.5) {
  slide.addText(text, {
    x: M, y, w, h: 0.55,
    fontFace: "Microsoft YaHei", fontSize: 14, color,
    margin: 0, breakLine: false,
  });
}
function footer(slide, n) {
  slide.addText("智购参谋  ·  全国人工智能应用创新大赛", {
    x: M, y: H - 0.38, w: 8.6, h: 0.2,
    fontSize: 8, color: C.muted, margin: 0,
  });
  slide.addText(String(n).padStart(2, "0"), {
    x: W - M - 0.4, y: H - 0.38, w: 0.4, h: 0.2,
    fontSize: 8, color: C.muted, align: "right", margin: 0,
  });
}
function card(slide, x, y, w, h, fill = C.paper) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.07,
    fill: { color: fill }, line: { color: C.line, width: 0.8 },
  });
}
function body(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x, y, w, h,
    fontFace: "Microsoft YaHei", fontSize: opts.size || 13.5,
    color: opts.color || C.brown, bold: opts.bold || false,
    margin: 0, valign: "top", fit: "shrink",
    breakLine: false, ...opts,
  });
}
function chip(slide, text, x, y, w, color = C.amber) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h: 0.3, rectRadius: 0.06,
    fill: { color: "F6EBDD" }, line: { color: "E8D3B7", width: 0.5 },
  });
  slide.addText(text, {
    x: x + 0.1, y: y + 0.045, w: w - 0.2, h: 0.2,
    fontSize: 9, bold: true, color, align: "center", margin: 0,
  });
}
function image(slide, file, x, y, w, h, cap) {
  slide.addImage({ path: path.join(SHOTS, file), x, y, w, h });
  if (cap) {
    slide.addText(cap, {
      x, y: y + h + 0.08, w, h: 0.25,
      fontSize: 8.5, color: C.muted, margin: 0,
    });
  }
}

/* ------------------------------------------------------------------ */
/* 01 Cover */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s, C.ink);
  image(s, "01-login.png", 7.25, 1.55, 5.35, 3.34);
  s.addText("全国人工智能应用创新大赛  ·  参赛作品", {
    x: 0.78, y: 0.78, w: 6.0, h: 0.3,
    fontSize: 11, bold: true, color: C.gold, charSpacing: 1.2, margin: 0,
  });
  s.addText("智购参谋", {
    x: 0.74, y: 1.55, w: 5.9, h: 0.9,
    fontSize: 48, bold: true, color: "FFFFFF", margin: 0,
  });
  s.addText("把一句购物需求，\n变成一份有依据的购买建议。", {
    x: 0.78, y: 2.65, w: 5.9, h: 1.25,
    fontSize: 22, color: "F7F0E4", bold: false,
    breakLine: true, margin: 0, lineSpacingMultiple: 1.1,
  });
  s.addText("面向笔记本电脑与手机的 AI 消费决策助手", {
    x: 0.78, y: 4.22, w: 5.9, h: 0.35,
    fontSize: 12.5, color: "CDBFA9", margin: 0,
  });
  s.addShape(pptx.ShapeType.line, {
    x: 0.8, y: 5.25, w: 5.5, h: 0,
    line: { color: "554B3B", width: 0.8 },
  });
  s.addText("20 件商品  /  2 个品类  /  1037 条自动化测试", {
    x: 0.8, y: 5.5, w: 5.8, h: 0.3,
    fontSize: 11, color: C.gold, margin: 0,
  });
  s.addText("在线演示：ai-shopping-10.streamlit.app", {
    x: 0.8, y: 5.95, w: 6.0, h: 0.3,
    fontSize: 9.5, color: "B7AA96", margin: 0,
  });
  s.addNotes("开场：这是一个把自然语言购物需求变成可解释推荐结果的 Web 应用。核心不是聊天，而是把预算、用途、商品数据和 AI 解释放在同一条可检查的链路里。");
}

/* ------------------------------------------------------------------ */
/* 02 Problem */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s);
  kicker(s, "01  /  问题");
  title(s, "买之前，缺的不是信息，而是取舍");
  subtitle(s, "商品页、评测、比价工具都在提供信息，但用户仍要自己回答：这次到底该选哪件。", C.muted, 1.7, 11.8);
  const items = [
    ["01", "参数口径不一", "同一项参数在不同品牌页面里的写法不同，横向比较成本很高。"],
    ["02", "评价不等于适配", "销量和口碑回答的是“大家怎么选”，不是“这次适不适合我”。"],
    ["03", "AI 会编造事实", "通用模型能理解需求，却可能顺口给出不存在价格、参数或排名。"],
  ];
  items.forEach((it, i) => {
    const x = M + i * 4.1;
    card(s, x, 2.55, 3.75, 2.25);
    s.addText(it[0], {
      x: x + 0.25, y: 2.78, w: 0.55, h: 0.35,
      fontSize: 12, bold: true, color: C.amber, margin: 0,
    });
    s.addText(it[1], {
      x: x + 0.25, y: 3.2, w: 3.25, h: 0.38,
      fontSize: 17, bold: true, color: C.ink, margin: 0,
    });
    s.addText(it[2], {
      x: x + 0.25, y: 3.72, w: 3.22, h: 0.85,
      fontSize: 12, color: C.muted, margin: 0, fit: "shrink",
    });
  });
  s.addText("智购参谋把“更多商品”换成“更清楚的取舍”：先明确预算与用途，再筛选、评分、解释。", {
    x: M, y: 5.35, w: 11.8, h: 0.45,
    fontSize: 15, bold: true, color: C.ink, margin: 0,
  });
  s.addText("它不替用户下单，也不假装自己是实时比价平台。", {
    x: M, y: 5.92, w: 11.8, h: 0.3,
    fontSize: 11, color: C.muted, margin: 0,
  });
  footer(s, 2);
  s.addNotes("问题部分不要讲成空泛的行业分析。用三个具体现象说明：参数不可比、评价不等同于需求匹配、模型会编造事实。");
}

/* ------------------------------------------------------------------ */
/* 03 Pipeline */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s);
  kicker(s, "02  /  产品");
  title(s, "一条可检查的决策链路");
  subtitle(s, "从一句自然语言开始，到一份能展开、能追溯、能存档的推荐报告。", C.muted, 1.7, 11.8);
  const steps = [
    ["01", "需求解析", "预算、品类、用途、偏好、硬性条件"],
    ["02", "候选筛选", "预算内与超预算商品分开展示"],
    ["03", "匹配评分", "按品类权重计算，不按价格排序"],
    ["04", "知识与工具", "RAG、商品库、受控 Agent"],
    ["05", "报告与存档", "评分构成、来源、历史快照"],
  ];
  steps.forEach((it, i) => {
    const x = M + i * 2.48;
    s.addShape(pptx.ShapeType.roundRect, {
      x, y: 2.55, w: 2.15, h: 1.75, rectRadius: 0.08,
      fill: { color: i === 2 ? "F3E3CE" : C.paper },
      line: { color: i === 2 ? "DDBB8C" : C.line, width: 0.8 },
    });
    s.addText(it[0], {
      x: x + 0.18, y: 2.72, w: 0.45, h: 0.25,
      fontSize: 10, bold: true, color: C.amber, margin: 0,
    });
    s.addText(it[1], {
      x: x + 0.18, y: 3.06, w: 1.8, h: 0.32,
      fontSize: 14.5, bold: true, color: C.ink, margin: 0,
    });
    s.addText(it[2], {
      x: x + 0.18, y: 3.48, w: 1.78, h: 0.58,
      fontSize: 9.5, color: C.muted, margin: 0, fit: "shrink",
    });
    if (i < steps.length - 1) {
      s.addShape(pptx.ShapeType.line, {
        x: x + 2.17, y: 3.4, w: 0.25, h: 0,
        line: { color: "C9B89F", width: 1.2, endArrowType: "triangle" },
      });
    }
  });
  card(s, M, 4.9, 11.95, 1.1, "F3E9DB");
  s.addText("规则负责排序，模型负责理解与表达。", {
    x: M + 0.35, y: 5.15, w: 7.0, h: 0.42,
    fontSize: 20, bold: true, color: C.ink, margin: 0,
  });
  s.addText("预算和硬性条件先过滤；AI 不参与分数、排序和历史快照。", {
    x: M + 7.4, y: 5.22, w: 4.15, h: 0.35,
    fontSize: 11, color: C.muted, margin: 0, align: "right",
  });
  footer(s, 3);
  s.addNotes("强调顺序：解析、筛选、评分、补充依据、存档。AI 是后置的解释与工具层，不是排序器。");
}

/* ------------------------------------------------------------------ */
/* 04 Same budget, three needs */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s);
  kicker(s, "03  /  演示");
  title(s, "同一笔预算，三种需求");
  subtitle(s, "2000 元不变，只改用途。第一名换了三次。", C.muted, 1.7, 11.8);
  const demos = [
    ["拍照优先", "真我 GT Neo6 SE", "1899 元", "81.6", "核心需求匹配 100 / 预算匹配 98"],
    ["续航优先", "iQOO Z9 Turbo", "1799 元", "81.5", "日常 + 续航命中，性能与价格平衡"],
    ["便携优先", "荣耀 X70", "1599 元", "62.2", "便携优先时仍是最高匹配，但绝对分不高"],
  ];
  demos.forEach((d, i) => {
    const x = M + i * 4.08;
    card(s, x, 2.55, 3.75, 2.75);
    chip(s, d[0], x + 0.22, 2.72, 1.2);
    s.addText(d[1], {
      x: x + 0.22, y: 3.2, w: 3.25, h: 0.38,
      fontSize: 16, bold: true, color: C.ink, margin: 0, fit: "shrink",
    });
    s.addText(d[2], {
      x: x + 0.22, y: 3.66, w: 1.5, h: 0.28,
      fontSize: 11, color: C.muted, margin: 0,
    });
    s.addText(d[3], {
      x: x + 2.55, y: 3.55, w: 0.95, h: 0.55,
      fontSize: 24, bold: true, color: C.amber, align: "right", margin: 0,
    });
    s.addText(d[4], {
      x: x + 0.22, y: 4.18, w: 3.25, h: 0.72,
      fontSize: 10.5, color: C.muted, margin: 0, fit: "shrink",
    });
  });
  s.addText("预算内 5 件，超预算 5 件单独列出；分数为当前数据的规则结果，商品更新后需重跑。", {
    x: M, y: 5.75, w: 11.95, h: 0.3,
    fontSize: 10.5, color: C.muted, margin: 0,
  });
  footer(s, 4);
  s.addNotes("三列分别展示三种用途。不要背成固定榜单，强调预算没变、排序随需求变化。截图和分数以现场应用为准。");
}

/* ------------------------------------------------------------------ */
/* 05 Scoring */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s);
  kicker(s, "04  /  可解释性");
  title(s, "评分不是黑盒");
  subtitle(s, "每个维度都有得分、权重和理由；缺失数据不补默认分。", C.muted, 1.7, 6.0);
  const rows = [
    ["预算匹配", "25%", "参考价占预算的比例"],
    ["核心需求匹配", "30%", "用途和核心偏好命中"],
    ["性能功能适配", "25%", "档位与用途的匹配"],
    ["性价比", "10%", "同类别性能与价格位置"],
    ["便携性", "10%", "重量与尺寸"],
  ];
  rows.forEach((r, i) => {
    const y = 2.5 + i * 0.62;
    s.addText(r[0], { x: M, y, w: 1.65, h: 0.3, fontSize: 12, bold: true, color: C.ink, margin: 0 });
    s.addText(r[1], { x: M + 1.85, y, w: 0.55, h: 0.3, fontSize: 12, bold: true, color: C.amber, margin: 0 });
    s.addText(r[2], { x: M + 2.6, y, w: 3.2, h: 0.3, fontSize: 10.5, color: C.muted, margin: 0 });
  });
  s.addShape(pptx.ShapeType.line, { x: M, y: 5.62, w: 6.05, h: 0, line: { color: C.line, width: 0.8 } });
  s.addText("总分 = Σ（维度得分 × 品类权重）", {
    x: M, y: 5.8, w: 6.2, h: 0.35,
    fontSize: 14, bold: true, color: C.ink, margin: 0,
  });
  s.addText("手机权重示例；笔记本另有一套权重。", {
    x: M, y: 6.2, w: 6.0, h: 0.25, fontSize: 9.5, color: C.muted, margin: 0,
  });
  image(s, "03-analysis-rule.png", 6.72, 1.28, 5.95, 3.72);
  s.addText("“首选方案”展开后能看到每一项得分和理由。", {
    x: 6.72, y: 5.18, w: 5.95, h: 0.25, fontSize: 9, color: C.muted, margin: 0,
  });
  footer(s, 5);
  s.addNotes("这张图是全项目的核心：分数不是模型打分，而是预算、需求、性能、性价比、便携性的加权。缺失维度会被排除，并在页面上注明。");
}

/* ------------------------------------------------------------------ */
/* 06 Compare */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s);
  kicker(s, "05  /  比较");
  title(s, "把差异摊在同一张表里");
  subtitle(s, "先选品类，再选 2–5 件商品；缺失数据直接标出，不拿别的商品补。", C.muted, 1.7, 6.0);
  const points = [
    ["同类才有意义", "跨品类混选会被拒绝：手机和笔记本没有共同的性价比口径。"],
    ["差异优先", "参数表、差异维度、优缺点对照放在同一页，不用来回切商品页。"],
    ["缺数据就标注", "缺失字段写成“信息缺失”，不默认满足条件，也不填其他商品的值。"],
  ];
  points.forEach((p, i) => {
    const y = 2.55 + i * 1.18;
    s.addShape(pptx.ShapeType.ellipse, {
      x: M, y: y + 0.03, w: 0.28, h: 0.28,
      fill: { color: "F1E2CE" }, line: { color: "E1C49F", width: 0.5 },
    });
    s.addText(String(i + 1), {
      x: M, y: y + 0.075, w: 0.28, h: 0.16,
      fontSize: 8, bold: true, color: C.amber, align: "center", margin: 0,
    });
    s.addText(p[0], {
      x: M + 0.48, y: y - 0.02, w: 2.0, h: 0.3,
      fontSize: 14, bold: true, color: C.ink, margin: 0,
    });
    s.addText(p[1], {
      x: M + 2.5, y: y - 0.02, w: 3.45, h: 0.75,
      fontSize: 10.5, color: C.muted, margin: 0, fit: "shrink",
    });
  });
  image(s, "05-compare-filled.png", 6.72, 1.26, 5.95, 4.13);
  footer(s, 6);
  s.addNotes("比较页不是推荐页的重复：推荐页回答“哪几款值得看”，比较页回答“这几款差在哪”。缺失数据不填充是本项目的一个硬约束。");
}

/* ------------------------------------------------------------------ */
/* 07 AI Q&A */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s);
  kicker(s, "06  /  问答");
  title(s, "答案要落到具体商品");
  subtitle(s, "知识库优先；具体商品问题从商品库取候选，再让模型组织回答。", C.muted, 1.7, 6.1);
  const q = [
    ["知识库", "品类指南、FAQ、商品级条目；向量检索失败回退 BM25。"],
    ["商品库", "“2000 元以内手机推荐”会先取 5 件真实候选。"],
    ["通用知识", "资料不足时补充，但界面明确标注“未引用知识库”。"],
  ];
  q.forEach((p, i) => {
    const y = 2.55 + i * 1.1;
    s.addText(p[0], {
      x: M, y, w: 1.05, h: 0.3,
      fontSize: 11, bold: true, color: C.amber, margin: 0,
    });
    s.addText(p[1], {
      x: M + 1.2, y: y - 0.02, w: 4.5, h: 0.7,
      fontSize: 11, color: C.muted, margin: 0, fit: "shrink",
    });
  });
  s.addText("价格来自商品库或资料，且仍是参考价；不冒充实时价。", {
    x: M, y: 5.82, w: 5.9, h: 0.3,
    fontSize: 10, color: C.muted, margin: 0,
  });
  image(s, "04-ai-qa.png", 6.7, 1.24, 6.0, 3.75);
  s.addText("实际回答：给出 3 款手机、参考价和匹配理由。", {
    x: 6.7, y: 5.1, w: 6.0, h: 0.25, fontSize: 9, color: C.muted, margin: 0,
  });
  footer(s, 7);
  s.addNotes("这一页要现场演示或播放录屏：输入“2000 元以内手机推荐”，等待回答，指出 5 件候选和具体型号。强调价格校验和通用知识标注。");
}

/* ------------------------------------------------------------------ */
/* 08 RAG + Agent */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s);
  kicker(s, "07  /  技术");
  title(s, "RAG 给依据，Agent 给路径");
  subtitle(s, "检索和工具都受同一组边界约束，失败时回到确定性管道。", C.muted, 1.7, 11.8);
  card(s, M, 2.45, 5.6, 3.45);
  s.addText("知识库", { x: M + 0.28, y: 2.68, w: 4.5, h: 0.35, fontSize: 18, bold: true, color: C.ink, margin: 0 });
  s.addText([
    { text: "23 篇资料 · 38 个切片 · 38 个已向量化", options: { bullet: true, breakLine: true } },
    { text: "2 份品类指南 + FAQ + 商品级合成条目", options: { bullet: true, breakLine: true } },
    { text: "向量优先，调用失败回退中文二元组 + BM25", options: { bullet: true, breakLine: true } },
    { text: "单次最多 3 条，阈值 + 相对截断", options: { bullet: true } },
  ], {
    x: M + 0.28, y: 3.18, w: 4.95, h: 2.1,
    fontSize: 11.5, color: C.muted, paraSpaceAfter: 8, margin: 0, fit: "shrink",
  });
  card(s, 6.62, 2.45, 5.95, 3.45);
  s.addText("受控 Agent", { x: 6.9, y: 2.68, w: 4.5, h: 0.35, fontSize: 18, bold: true, color: C.ink, margin: 0 });
  s.addText([
    { text: "4 个只读工具：筛选、详情、比较、知识检索", options: { bullet: true, breakLine: true } },
    { text: "最多 5 轮；工具参数经过 pydantic + 业务校验", options: { bullet: true, breakLine: true } },
    { text: "执行轨迹记录真实调用，不记录思考文字", options: { bullet: true, breakLine: true } },
    { text: "失败或超时回到确定性管道，基础功能不空白", options: { bullet: true } },
  ], {
    x: 6.9, y: 3.18, w: 5.3, h: 2.1,
    fontSize: 11.5, color: C.muted, paraSpaceAfter: 8, margin: 0, fit: "shrink",
  });
  s.addText("工具集没有写库、执行 SQL 或对外请求的入口。", {
    x: M, y: 6.15, w: 11.9, h: 0.3,
    fontSize: 10.5, color: C.muted, margin: 0,
  });
  footer(s, 8);
  s.addNotes("技术页不要堆框架名。讲三个数字和三个边界：23 篇资料、4 个工具、5 轮上限；工具只读、参数校验、失败降级。");
}

/* ------------------------------------------------------------------ */
/* 09 Anti-hallucination */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s);
  kicker(s, "08  /  可信度");
  title(s, "让 AI 只做它该做的事");
  subtitle(s, "事实由商品库提供，排序由规则完成，AI 负责解释。", C.muted, 1.7, 11.8);
  const items = [
    ["知识问答", "检查价格和排他性结论；不通过就丢弃整条回答。"],
    ["商品问答", "价格必须来自商品库、资料或用户问题；商品名仍主要靠提示词约束。"],
    ["Agent 最终说明", "工具参数有校验；最终文本没有走完整事实校验，界面提示以工具数据为准。"],
    ["排序与历史", "AI 不参与评分、排序；历史报告只存规则快照。"],
  ];
  items.forEach((it, i) => {
    const x = M + (i % 2) * 6.1;
    const y = 2.45 + Math.floor(i / 2) * 1.75;
    card(s, x, y, 5.75, 1.45);
    s.addText(it[0], {
      x: x + 0.24, y: y + 0.2, w: 2.0, h: 0.28,
      fontSize: 13, bold: true, color: C.ink, margin: 0,
    });
    s.addText(it[1], {
      x: x + 0.24, y: y + 0.58, w: 5.2, h: 0.65,
      fontSize: 10.5, color: C.muted, margin: 0, fit: "shrink",
    });
  });
  s.addText("边界写清楚，比“永不幻觉”更可信。", {
    x: M, y: 6.05, w: 11.8, h: 0.35,
    fontSize: 14, bold: true, color: C.ink, margin: 0,
  });
  footer(s, 9);
  s.addNotes("这一页主动讲限制：商品问答没有完整的商品名实体校验，Agent 最终文本也没有全量事实校验。评委会更信任一个知道边界的团队。");
}

/* ------------------------------------------------------------------ */
/* 10 Evidence */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s);
  kicker(s, "09  /  工程");
  title(s, "不是只靠一段演示");
  subtitle(s, "自动化测试、效果评测和真实数据口径分开记录。", C.muted, 1.7, 11.8);
  const stats = [
    ["1037", "条自动化测试", "34 个测试文件，退出码 0"],
    ["41", "条效果评测", "需求、边界、检索、幻觉、比较"],
    ["20", "件商品", "2 个品类 · 13 个品牌"],
    ["20/20", "逐条来源链接", "全部未核验，参考价非实时"],
  ];
  stats.forEach((st, i) => {
    const x = M + i * 3.02;
    card(s, x, 2.4, 2.7, 1.65);
    s.addText(st[0], {
      x: x + 0.22, y: 2.54, w: 2.2, h: 0.55,
      fontSize: 26, bold: true, color: C.amber, margin: 0,
    });
    s.addText(st[1], {
      x: x + 0.22, y: 3.1, w: 2.2, h: 0.28,
      fontSize: 11.5, bold: true, color: C.ink, margin: 0,
    });
    s.addText(st[2], {
      x: x + 0.22, y: 3.42, w: 2.2, h: 0.5,
      fontSize: 8.5, color: C.muted, margin: 0, fit: "shrink",
    });
  });
  s.addText("自动指标（自建 41 条用例）", {
    x: M, y: 4.55, w: 5.2, h: 0.28,
    fontSize: 11, bold: true, color: C.ink, margin: 0,
  });
  s.addText("需求理解 25/25   ·   硬性条件 9/9   ·   检索 17/17   ·   幻觉 6/6   ·   相关性 9/9", {
    x: M, y: 4.92, w: 7.2, h: 0.35,
    fontSize: 10, color: C.muted, margin: 0,
  });
  s.addText("这是自评，不是第三方基准；任务完成率和证据支持率仍需人工测量。", {
    x: M, y: 5.55, w: 11.8, h: 0.3,
    fontSize: 10, color: C.muted, margin: 0,
  });
  s.addText("把“能演示”与“可验证”分开写，比赛材料才不会虚。", {
    x: M, y: 6.05, w: 11.8, h: 0.3,
    fontSize: 12, bold: true, color: C.ink, margin: 0,
  });
  footer(s, 10);
  s.addNotes("数字要背下来：1037 条测试、34 个文件、41 条评测、20 件商品、20/20 来源链接。强调自评边界，不把 100% 说成系统整体质量。");
}

/* ------------------------------------------------------------------ */
/* 11 Limits */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s);
  kicker(s, "10  /  边界");
  title(s, "边界写清楚，演示才可信");
  subtitle(s, "当前版本适合比赛与教学，不是实时交易系统。", C.muted, 1.7, 11.8);
  const limits = [
    ["数据规模", "20 件商品、2 个品类，未逐条核验；价格是参考价。"],
    ["实时能力", "不接电商平台，没有实时价格、库存、销量和真实评价。"],
    ["部署形态", "Streamlit + SQLite；Cloud 文件系统临时，休眠或重部署可能重置。"],
    ["账号体系", "演示级鉴权：无登录限流、无会话过期，公开演示不输入真实个人信息。"],
  ];
  limits.forEach((it, i) => {
    const x = M + (i % 2) * 6.1;
    const y = 2.45 + Math.floor(i / 2) * 1.5;
    card(s, x, y, 5.75, 1.2);
    s.addText(it[0], {
      x: x + 0.24, y: y + 0.16, w: 2.0, h: 0.28,
      fontSize: 13, bold: true, color: C.ink, margin: 0,
    });
    s.addText(it[1], {
      x: x + 0.24, y: y + 0.55, w: 5.2, h: 0.48,
      fontSize: 10.5, color: C.muted, margin: 0, fit: "shrink",
    });
  });
  s.addText("下一步：授权商品数据 → 持久化数据库 → 人工评测与用户测试 → 再扩品类。", {
    x: M, y: 5.75, w: 11.8, h: 0.35,
    fontSize: 12, bold: true, color: C.ink, margin: 0,
  });
  footer(s, 11);
  s.addNotes("不要试图掩盖数据少、没有实时价。比赛里主动讲边界，比被评委问出来更好。");
}

/* ------------------------------------------------------------------ */
/* 12 Close */
/* ------------------------------------------------------------------ */
{
  const s = pptx.addSlide();
  bg(s, C.ink);
  s.addText("智购参谋", {
    x: 0.8, y: 1.55, w: 8.0, h: 0.8,
    fontSize: 44, bold: true, color: "FFFFFF", margin: 0,
  });
  s.addText("把推荐理由摊开，\n让每一次选择都能回到数据。", {
    x: 0.84, y: 2.55, w: 8.6, h: 1.25,
    fontSize: 24, color: "F7F0E4", margin: 0, breakLine: true, lineSpacingMultiple: 1.15,
  });
  s.addText("在线演示", {
    x: 0.86, y: 4.55, w: 2.0, h: 0.3,
    fontSize: 10, bold: true, color: C.gold, margin: 0,
  });
  s.addText("ai-shopping-10.streamlit.app", {
    x: 0.86, y: 4.9, w: 8.8, h: 0.3,
    fontSize: 12, color: "D8CCB9", margin: 0,
  });
  s.addText("代码仓库  github.com/sxxzy-a11y/ai-shopping", {
    x: 0.86, y: 5.35, w: 7.0, h: 0.3,
    fontSize: 10, color: "B7AA96", margin: 0,
  });
  s.addText("谢谢", {
    x: 10.6, y: 5.8, w: 1.9, h: 0.5,
    fontSize: 18, color: C.gold, align: "right", margin: 0,
  });
  s.addNotes("结尾不要再堆功能。回到一句话：把推荐理由摊开，让选择回到数据。");
}

pptx.writeFile({ fileName: path.resolve("submission/智购参谋_比赛演示.pptx") });
