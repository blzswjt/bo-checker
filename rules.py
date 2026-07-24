"""
数据建模识别规范 - 所有元素类型的规则知识库
包含：主题域分类、主题域分组、主题域、业务对象、逻辑实体、业务属性
"""
import json

# 所有支持的元素类型
ELEMENT_TYPES = [
    "主题域分类", "主题域分组", "主题域",
    "业务对象", "逻辑实体", "业务属性"
]

# ============================================================
# 各元素类型的识别规则
# ============================================================

ELEMENT_RULES = {
    "主题域分类": {
        "description": "与BA的流程架构L1对齐的最高层级分类",
        "identification": [
            {"rule": "与BA对齐", "desc": "同BA的流程架构L1对齐", "positive": "管理采购", "negative": ""}
        ],
        "naming": [
            {"rule": "全局唯一", "desc": "全局唯一，无歧义", "positive": "管理采购", "negative": ""}
        ],
        "not_examples": [],
    },
    "主题域分组": {
        "description": "与BA的流程架构L2对齐的分组",
        "identification": [
            {"rule": "与BA对齐", "desc": "同BA的流程架构L2对齐", "positive": "管理采购履行", "negative": ""}
        ],
        "naming": [
            {"rule": "全局唯一", "desc": "全局唯一，无歧义", "positive": "管理采购履行", "negative": ""}
        ],
        "not_examples": [],
    },
    "主题域": {
        "description": "与BA的流程架构L3对齐的主题域",
        "identification": [
            {"rule": "与BA对齐", "desc": "同BA的流程架构L3对齐", "positive": "管理采购需求", "negative": ""}
        ],
        "naming": [
            {"rule": "全局唯一", "desc": "全局唯一，无歧义", "positive": "管理采购需求", "negative": ""}
        ],
        "not_examples": [],
    },
    "业务对象": {
        "description": "企业运作和管理过程中不可缺少的重要人、事、物、地信息",
        "identification": [
            {"rule": "企业运作中不可缺少的重要人、事、物、地信息", "desc": "来源于业务流程的表、证、单、书，而非IT系统视角。通常会建立相应流程、组织和IT进行管理。",
             "positive": "采购需求作为采购流程的源头单据，承接前端业务需求，驱动货源确认、订单下达、到货验收等环节", "negative": ""},
            {"rule": "有唯一的身份标识信息", "desc": "有唯一性身份标识信息，能区分业务对象的实例，且标识不变",
             "positive": "采购需求有采购需求编号唯一标识", "negative": "采购需求行没有独立的身份标识，不是业务对象"},
            {"rule": "相对独立并有一组实体描述", "desc": "可独立存在、获取、传输、使用并发挥价值",
             "positive": "采购需求与供应商、采购订单等业务对象相对独立", "negative": "采购需求行不能独立存在，依赖于采购需求头"},
            {"rule": "有生命周期和状态变化", "desc": "有生命周期，有状态变化",
             "positive": "采购需求有状态：草稿、审核中、已审批、已驳回、已作废", "negative": "基础数据/观测数据无状态变化"},
            {"rule": "可实例化", "desc": "实例可发生业务行为，实例集合不可提前预知、不限定数量",
             "positive": "采购需求有很多次需求，有创建、审批、退回、取消等行为", "negative": "基础数据是分类/标签，无业务行为；报告报表数据无法实例化"},
        ],
        "naming": [
            {"rule": "名称唯一", "desc": "名称在数据模型中具有唯一性", "positive": "采购需求", "negative": "直接采购需求和间接采购需求如果属性不同，需拆分为不同业务对象且名称不能相同"},
            {"rule": "名词命名", "desc": "必须是名词，不使用虚词，避免英文和符号，首尾不使用数字", "positive": "采购需求", "negative": "采购需求申请"},
            {"rule": "符合行规", "desc": "符合企业内、行业内的通用习惯和规范", "positive": "采购需求", "negative": "采购需求申请单"},
        ],
        "not_examples": [
            "基础数据/码值/分类/标签（如：采购需求类型、币种、国家代码）",
            "业务对象的子实体/行项目（如：采购需求行、订单明细行）",
            "观测数据/报告/报表数据",
            "属性/字段（如：金额、日期、数量）",
            "操作/动作/行为（如：审批、提交）",
            "系统/模块/功能（如：采购系统、报表模块）",
        ],
        "definition": [
            {"rule": "编码唯一", "desc": "业务对象元素的编码在企业内唯一，并遵循相同的编码规范", "positive": "BOPUR001（BO+领域缩写+3位序列号）", "negative": ""},
            {"rule": "描述内容完整", "desc": "业务对象应有明确描述，包括目的（为什么）、定义（是什么）和范围（含哪些），范围不应局限于某类产品", "positive": "采购需求是企业对物资/服务的采购申请与业务承诺，驱动采购计划与订单下达", "negative": ""},
        ],
    },
    "逻辑实体": {
        "description": "业务对象下描述某方面特征的逻辑数据实体",
        "identification": [
            {"rule": "主逻辑实体唯一", "desc": "每个业务对象有且只有一个主逻辑实体",
             "positive": "业务对象'采购需求'中包含一个'采购需求头'主逻辑实体", "negative": "包含'采购需求头'和'采购需求行'两个主逻辑实体"},
            {"rule": "剔除技术数据和衍生数据", "desc": "逻辑实体原则上不包括技术数据和衍生数据",
             "positive": "", "negative": "采购需求发布任务表、采购订单接口头表、采购需求行宽表"},
            {"rule": "关系实体归属原则", "desc": "按先后顺序、概率判断或业务主责归属",
             "positive": "采购需求关系归属于业务对象'采购需求'", "negative": "'采购订单关系'不应归属于'采购需求'，应归属于'采购订单'"},
            {"rule": "高内聚", "desc": "相似度较高且可聚类的属性可抽象出逻辑实体", "positive": "", "negative": ""},
            {"rule": "逻辑实体拆分", "desc": "属性较多较散乱时需按业务视角分组拆分",
             "positive": "采购需求行拆分为：基本信息、物料与规格、数量与单位等", "negative": "不做拆分，一个逻辑实体包含100多个属性"},
            {"rule": "逻辑实体嵌套", "desc": "拆分后采用嵌套关系，上级包含下级，可做树形多级嵌套",
             "positive": "采购需求行包含9个下级逻辑实体", "negative": "拆分后建立1:1的ER关系而非嵌套"},
        ],
        "naming": [
            {"rule": "名称唯一", "desc": "实体命名在数据模型中具有唯一性", "positive": "采购需求头", "negative": "存在多个重复的'采购需求头'"},
            {"rule": "下层加前缀", "desc": "下层实体应以上层实体名词作为前缀或后缀扩展", "positive": "", "negative": ""},
            {"rule": "名词命名", "desc": "必须是名词", "positive": "采购需求头", "negative": "采购申请"},
            {"rule": "避免虚词", "desc": "不使用虚词、英文、符号，首尾不用数字", "positive": "采购需求头", "negative": "采购需求头1"},
            {"rule": "符合行规", "desc": "符合企业和行业通用习惯", "positive": "供应商账户", "negative": "供应商帐户（应用'账'不用'帐'）"},
            {"rule": "关系实体命名规范", "desc": "格式为'实体1和实体2关系'", "positive": "采购需求和采购订单分摊关系", "negative": "采购订单分摊关系"},
            {"rule": "剔除特定关键字", "desc": "不能带'表、文件、菜单、报告'等关键字（特定业务场景除外）", "positive": "采购需求头", "negative": "采购需求头表"},
        ],
        "not_examples": [
            "技术数据表（如：接口表、发布任务表）",
            "衍生数据（如：宽表、汇总表）",
            "独立的业务对象（逻辑实体必须依附于业务对象）",
        ],
        "definition": [
            {"rule": "编码唯一", "desc": "逻辑实体元素的编码在企业内唯一，并遵循相同的编码规范", "positive": "LEPUR0001（LE+领域缩写+4位序列号）", "negative": ""},
            {"rule": "必须有主键", "desc": "实体应具有业务主键，且业务主键在生命周期内不改变", "positive": "采购需求头的主键是“采购需求编号”", "negative": ""},
            {"rule": "主键稳定", "desc": "标识符的取值在其生命周期过程中不应变化或废止", "positive": "采购需求编号一经产生，就不会被修改", "negative": ""},
            {"rule": "主键有业务含义", "desc": "主键有业务含义，所有用户可获取、理解和使用", "positive": "采购需求编号280020260604000004标识管理单元2800下2026年6月4日第4单需求", "negative": ""},
            {"rule": "实体归属唯一", "desc": "逻辑实体必须归属于唯一的业务对象", "positive": "采购需求关系、采购需求行关系归属于业务对象“采购需求”", "negative": ""},
            {"rule": "描述内容完整", "desc": "逻辑实体应有明确描述，包括目的、定义和范围", "positive": "采购需求头：是一份采购需求申请单的摘要和控制信息", "negative": ""},
        ],
    },
    "业务属性": {
        "description": "逻辑实体下最小业务语义单元",
        "identification": [
            {"rule": "原子性", "desc": "最小业务语义单元，不可再拆分",
             "positive": "采购需求行号", "negative": "采购需求行（这是逻辑实体，不是属性）"},
            {"rule": "必要性", "desc": "每个属性都有明确含义和用途，满足业务需求",
             "positive": "采购需求行中包含'需求日期'", "negative": "采购需求行中包含'发货日期'（不属于采购需求）"},
            {"rule": "剔除技术字段", "desc": "无业务含义的技术字段不作为属性纳入",
             "positive": "", "negative": "租户ID、删除标记、创建人、最后修改人等"},
        ],
        "naming": [
            {"rule": "业务词汇", "desc": "采用正式业务词汇", "positive": "物料编码", "negative": "原料编码（太口语化）"},
            {"rule": "名称贯标", "desc": "企业级唯一且共享，与数据标准一致", "positive": "采购需求编号（数据标准定义）", "negative": "采购需求号码"},
            {"rule": "顾名思义", "desc": "名称清晰、见名知义", "positive": "采购单价", "negative": "请购单价"},
            {"rule": "词汇简练", "desc": "用尽可能简练的词汇", "positive": "自动创建标识", "negative": "采购需求自动创建标识"},
            {"rule": "少用特殊字符", "desc": "避免程序和SQL关键词、运算符号等", "positive": "", "negative": "名称包含&、-、+、/、*等"},
        ],
        "not_examples": [
            "技术字段（租户ID、删除标记、创建人等）",
            "逻辑实体（如采购需求行是实体不是属性）",
            "可拆分的复合字段",
        ],
        "definition": [],
    },
}


# ============================================================
# 用于 LLM 判断的 Prompt 模板
# ============================================================

def build_check_prompt(element_type: str) -> str:
    """根据元素类型构建识别 Prompt"""
    rules = ELEMENT_RULES.get(element_type)
    if not rules:
        return ""

    parts = [f"你是一个数据治理专家，专门负责判断某个事物是否符合「{element_type}」的定义。"]
    parts.append(f"\n## {element_type}的定义\n{rules['description']}")

    # 识别规则
    parts.append(f"\n## 识别规则（需全部满足）")
    for i, r in enumerate(rules["identification"], 1):
        parts.append(f"\n{i}. **{r['rule']}**：{r['desc']}")
        if r.get("positive"):
            parts.append(f"   - 正例：{r['positive']}")
        if r.get("negative"):
            parts.append(f"   - 反例：{r['negative']}")

    # 命名规则
    parts.append(f"\n## 命名规则")
    for i, r in enumerate(rules["naming"], 1):
        parts.append(f"\n{i}. **{r['rule']}**：{r['desc']}")
        if r.get("positive"):
            parts.append(f"   - 正例：{r['positive']}")
        if r.get("negative"):
            parts.append(f"   - 反例：{r['negative']}")

    # 常见反例
    if rules.get("not_examples"):
        parts.append(f"\n## 常见不是{element_type}的情况")
        for ex in rules["not_examples"]:
            parts.append(f"- {ex}")

    parts.append(f"""
## 判断要求
请对给定的事物逐条规则分析，最后给出明确结论。

输出格式：
- **结论：** ✅ 是{element_type} / ❌ 不是{element_type} / ⚠️ 无法确定
- **理由：** 逐条规则分析""")

    return "\n".join(parts)


def build_batch_prompt(element_type: str, items_text: str, kb_examples: dict = None) -> str:
    """构建批量识别 Prompt，集成知识库示例和逐条规则分析"""
    rules = ELEMENT_RULES.get(element_type)
    if not rules:
        return ""

    # 规则详情 - 包含所有规则类型
    id_rules = rules["identification"]
    nm_rules = rules.get("naming", [])
    df_rules = rules.get("definition", [])
    
    id_detail = ""
    for i, r in enumerate(id_rules, 1):
        id_detail += f"\n{i}. 【{r['rule']}】{r['desc']}"
        if r.get("positive"):
            id_detail += f"（正例：{r['positive']}）"
        if r.get("negative"):
            id_detail += f"（反例：{r['negative']}）"

    nm_detail = ""
    if nm_rules:
        for i, r in enumerate(nm_rules, 1):
            nm_detail += f"\n{i}. 【{r['rule']}】{r['desc']}"
            if r.get("positive"):
                nm_detail += f"（正例：{r['positive']}）"
            if r.get("negative"):
                nm_detail += f"（反例：{r['negative']}）"

    df_detail = ""
    if df_rules:
        for i, r in enumerate(df_rules, 1):
            df_detail += f"\n{i}. 【{r['rule']}】{r['desc']}"
            if r.get("positive"):
                df_detail += f"（正例：{r['positive']}）"
            if r.get("negative"):
                df_detail += f"（反例：{r['negative']}）"

    not_summary = ""
    if rules.get("not_examples"):
        not_summary = "\n常见不是的情况：" + "；".join(rules["not_examples"][:4])

    # 知识库已知示例
    kb_section = ""
    if kb_examples:
        pos = kb_examples.get("positive", [])
        neg = kb_examples.get("negative", [])
        if pos or neg:
            kb_section = "\n\n## 已知参考（用户已确认，请优先参考）"
            if pos:
                kb_section += "\n已确认是的：" + "、".join(f"{e['item']}（{e.get('reason','')}）" for e in pos[:6])
            if neg:
                kb_section += "\n已确认不是的：" + "、".join(f"{e['item']}（{e.get('reason','')}）" for e in neg[:6])

    # 构建所有规则名称列表供逐条分析
    all_rule_names = [r["rule"] for r in id_rules] + [r["rule"] for r in nm_rules] + [r["rule"] for r in df_rules]
    rule_names_json = json.dumps(all_rule_names, ensure_ascii=False)

    return f"""你是一个数据治理专家。请判断以下事物是否是「{element_type}」。

## {element_type}定义
{rules['description']}

## 识别规则（需全部满足）{id_detail}

## 命名规则{nm_detail}

## 定义规则{df_detail}{not_summary}{kb_section}

## 输出要求

**第一步：先用自然语言对每个事物进行分析思考**

对每个事物逐条规则分析（包括识别规则、命名规则、定义规则），格式如：
**1. 事物名**
- 分析：简要分析这个事物是什么，与{element_type}的关系
- 规则判断：
  - ✓/✗ 【规则名】满足或不满足的原因
- 结论：是/不是/待人工

**第二步：最后输出JSON结果**

分析完所有事物后，输出最终JSON：
```json
{{"results": [{{
  "item": "事物名",
  "is_bo": true/false/null,
  "confidence": "high/medium/low",
  "reason": "总体简要理由",
  "rules_check": [{{"rule": "规则名", "pass": true/false, "reason": "满足或不满足的简要原因"}}]
}}]}}
```

说明：
- is_bo: true=是{element_type}, false=不是, null=无法确定需人工判断
- rules_check: 对所有规则（识别+命名+定义）逐一判断，rule名必须与上面的规则名完全一致

规则名列表：{rule_names_json}

待判断的事物列表：
{items_text}"""


def get_all_rules_text() -> dict:
    """返回所有元素类型的规则文本，供前端展示"""
    result = {}
    for etype, rules in ELEMENT_RULES.items():
        parts = [f"# {etype}\n{rules['description']}\n"]
        parts.append("## 识别规则")
        for r in rules["identification"]:
            parts.append(f"- **{r['rule']}**：{r['desc']}")
        parts.append("\n## 命名规则")
        for r in rules["naming"]:
            parts.append(f"- **{r['rule']}**：{r['desc']}")
        if rules.get("definition"):
            parts.append("\n## 定义规则")
            for r in rules["definition"]:
                parts.append(f"- **{r['rule']}**：{r['desc']}")
        if rules.get("not_examples"):
            parts.append("\n## 常见反例")
            for ex in rules["not_examples"]:
                parts.append(f"- {ex}")
        result[etype] = "\n".join(parts)
    return result


def get_rule_detail(etype: str, rule_name: str) -> str:
    """获取某条规则的详细描述，用于答疑智能体"""
    rules = ELEMENT_RULES.get(etype, {})
    for category in ["identification", "naming", "definition"]:
        for r in rules.get(category, []):
            if r["rule"] == rule_name or rule_name in r["rule"] or r["rule"] in rule_name:
                cat_name = {"identification": "识别规则", "naming": "命名规则", "definition": "定义规则"}.get(category, category)
                return f"规则类别：{cat_name}\n规则名称：{r['rule']}\n规则描述：{r['desc']}"
    return f"规则名称：{rule_name}\n（未找到详细描述）"


# 列名关键词 → 元素类型推荐映射
COLUMN_TYPE_KEYWORDS = {
    "主题域分类": ["主题域分类", "分类名称", "L1"],
    "主题域分组": ["主题域分组", "分组名称", "L2"],
    "主题域": ["主题域名称", "主题域", "L3"],
    "业务对象": ["业务对象唯一标识", "业务对象名称", "业务对象编码", "业务对象"],
    "逻辑实体": ["逻辑实体名称", "逻辑实体唯一标识", "逻辑实体编码", "逻辑实体"],
    "业务属性": ["属性名称", "属性唯一标识", "属性编码", "业务属性", "业务属性名称"],
}


def recommend_element_type(column_name: str) -> str | None:
    """根据列名推荐最可能的元素类型"""
    col = column_name.strip()
    for etype, keywords in COLUMN_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in col:
                return etype
    return None
