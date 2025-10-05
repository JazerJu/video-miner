import re
from typing import List, Tuple

def parse_srt_file(filepath: str) -> List[Tuple[str, float, float, str]]:
    """
    读取SRT文件并解析为 (index, start_time, end_time, text) 的列表
    """
    pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)\n\n', re.DOTALL)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read() + '\n\n'
    matches = pattern.findall(content)
    results = []
    for m in matches:
        idx = m[0]
        start = _srt_time_to_seconds(m[1])
        end = _srt_time_to_seconds(m[2])
        text = m[3].replace('\n', ' ').strip()
        results.append((idx, start, end, text))
    return results

def _srt_time_to_seconds(t: str) -> float:
    """
    将 SRT 时间格式 (HH:MM:SS,mmm) 转换为秒
    """
    h, m, s_milli = t.split(':')
    s, milli = s_milli.split(',')
    return int(h)*3600 + int(m)*60 + int(s) + int(milli)/1000.0

def split_subtitles(subs: List[Tuple[str, float, float, str]],
                    max_chars=1000,
                    max_words=800,
                    look_ahead_chars=120,
                    look_ahead_words=80) -> List[List[Tuple[str, float, float, str]]]:
    """
    将字幕按每千字（或800英文词）划分，并在前后 look_ahead_chars / look_ahead_words 范围内
    寻找最大的时间间隔——以此为最终切分点，返回分段后的字幕数据列表。
    """
    segments = []
    current_segment = []
    current_char_count = 0
    current_word_count = 0

    for i, (idx, start, end, text) in enumerate(subs):
        # 统计中英字符与词
        text_char_count = len(text)
        text_word_count = len(text.split())

        # 若加入本字幕后超出阈值，则尝试寻找最佳切分点
        if (current_char_count + text_char_count > max_chars) or (current_word_count + text_word_count > max_words):
            # 在回溯和前瞻范围内，寻找最大时间间隔
            cut_index = i  # 初步划分点
            best_gap = 0
            best_index = cut_index
            # 回溯到 i - look_ahead
            start_look = max(0, i - look_ahead_chars)
            end_look = min(len(subs), i + look_ahead_chars)
            for j in range(start_look, end_look):
                if j+1 < len(subs):
                    gap = subs[j+1][1] - subs[j][2]
                    # 寻找最大时间间隔
                    if gap > best_gap:
                        best_gap = gap
                        best_index = j + 1
            # 到最佳索引处切分
            segments.append(current_segment)
            current_segment = []
            current_char_count = 0
            current_word_count = 0

            # 将剩余部分从最佳索引开始处理
            for k in range(best_index, i):
                current_segment.append(subs[k])
                current_char_count += len(subs[k][3])
                current_word_count += len(subs[k][3].split())

        # 累计加上当前字幕
        current_segment.append((idx, start, end, text))
        current_char_count += text_char_count
        current_word_count += text_word_count

    # 剩余的字幕放到最后一段
    if current_segment:
        segments.append(current_segment)
    return segments

def call_gpt4o_mini_for_segment(segment_text: str, client) -> str:
    """
    调用GPT方法，进行断句。client是OpenAI客户端对象
    """
    prompt = f"""你是一个负责拆分字幕的程序。 你的任务是将主体为简体中文的字幕拆分，保持口语语气和风格，避免长句子。我会告诉字幕内容的输入，他是一个 1000个字左右的纯文本，按照中文的语言习惯将它拆分，返回拆分后的段落，以<br>作为返回的拆分后句子的分隔。例如：

    **纯文本：**

    在一个宁静的小村庄里生活着一户勤劳善良的农民一家清晨天刚蒙蒙亮父亲就早早地起床开始了一天的劳作母亲在厨房忙碌为全家准备丰盛的早餐孩子们还在梦乡中等待着新一天的到来春天田野里绿油油的农民们挥动着锄头耕耘着希望的种子夏天麦浪翻滚阳光炽热大家辛勤地收割庄稼秋天果实累累农民们欢笑着收获丰收的喜悦冬天白雪覆盖大地村庄显得格外宁静除了耕作村民们还会在节日里聚集在一起共同庆祝分享快乐孩子们在村口的河边嬉戏老人们在大树下下棋聊天夜晚星空璀璨月光洒在屋顶上给人一种温馨的感觉村庄虽然简朴但充满了爱与温暖每个家庭成员都互相关心彼此支持共同面对生活的挑战这样的环境中孩子们健康快乐地成长承载着新一代的希望村庄的每一天都充满了生机与活力大家辛勤的劳动换来了美好的生活四季轮回年复一年村庄依然保持着它独特的宁静与和谐这里是人们心中永远的家园村庄周围环绕着青山绿水四周的山脉连绵起伏春天的时候山花烂漫夏天绿树成荫秋天红叶似火冬天银装素裹山间的小溪清澈见底鱼儿在水中欢快地游动鸟儿在枝头欢唱村民们常常在周末带着家人外出踏青享受大自然的美好每年的春耕时节村里会举办丰收节人们载歌载舞庆祝辛勤的劳动带来的收获秋收时农田里金黄一片喜悦的笑声充满了整个村庄冬天虽然寒冷但围炉夜话让人感到温暖村里的学校培养着一代又一代的孩子传承着村庄的文化和传统手工艺人在家中制作精美的工艺品成为远近闻名的特色产品随着时间的推移村庄也在不断发展新的道路和设施逐渐完善但人们依然保持着朴素的生活方式节假日里村民们会聚集在一起举办各种庆典活动增强了社区的凝聚力在这里人与自然和谐共处生活节奏缓慢而舒适孩子们在田野间奔跑老人们在树下休息年轻人在劳作中奋斗整个村庄充满了温馨和幸福人们用勤劳和智慧建设着自己的家园每一天都是新的开始每一个季节都有不同的美丽景色这样的生活虽然简单却充满了真实和满足成为人们心中永远美好的记忆

    **断句文本：**

    在一个宁静的小村庄里生活着一户勤劳善良的农民一家<br>清晨天刚蒙蒙亮父亲就早早地起床开始了一天的劳作<br>母亲在厨房忙碌为全家准备丰盛的早餐<br>孩子们还在梦乡中等待着新一天的到来<br>春天田野里绿油油的农民们挥动着锄头耕耘着希望的种子<br>夏天麦浪翻滚阳光炽热大家辛勤地收割庄稼<br>秋天果实累累农民们欢笑着收获丰收的喜悦<br>冬天白雪覆盖大地村庄显得格外宁静<br>除了耕作村民们还会在节日里聚集在一起共同庆祝分享快乐<br>孩子们在村口的河边嬉戏老人们在大树下下棋聊天<br>夜晚星空璀璨月光洒在屋顶上给人一种温馨的感觉<br>村庄虽然简朴但充满了爱与温暖<br>每个家庭成员都互相关心彼此支持共同面对生活的挑战<br>这样的环境中孩子们健康快乐地成长承载着新一代的希望<br>村庄的每一天都充满了生机与活力大家辛勤的劳动换来了美好的生活<br>四季轮回年复一年村庄依然保持着它独特的宁静与和谐这里是人们心中永远的家园<br>村庄周围环绕着青山绿水四周的山脉连绵起伏春天的时候山花烂漫夏天绿树成荫秋天红叶似火冬天银装素裹<br>山间的小溪清澈见底鱼儿在水中欢快地游动鸟儿在枝头欢唱<br>村民们常常在周末带着家人外出踏青享受大自然的美好<br>每年的春耕时节村里会举办丰收节人们载歌载舞庆祝辛勤的劳动带来的收获<br>秋收时农田里金黄一片喜悦的笑声充满了整个村庄<br>冬天虽然寒冷但围炉夜话让人感到温暖<br>村里的学校培养着一代又一代的孩子传承着村庄的文化和传统<br>手工艺人在家中制作精美的工艺品成为远近闻名的特色产品<br>随着时间的推移村庄也在不断发展新的道路和设施逐渐完善但人们依然保持着朴素的生活方式<br>节假日里村民们会聚集在一起举办各种庆典活动增强了社区的凝聚力<br>在这里人与自然和谐共处生活节奏缓慢而舒适<br>孩子们在田野间奔跑老人们在树下休息年轻人在劳作中奋斗整个村庄充满了温馨和幸福<br>人们用勤劳和智慧建设着自己的家园每一天都是新的开始每一个季节都有不同的美丽景色<br>这样的生活虽然简单却充满了真实和满足成为人们心中永远美好的记忆<br>

    以下是需要断句的文本：
    {segment_text}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        stream=False,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": segment_text}
            ],
        max_tokens=4096  # Ensure sufficient tokens for long responses
    )
    return response.choices[0].message.content

# 示例用法
if __name__ == "__main__":
    # 从 SRT 读取
    srt_data = parse_srt_file("output.srt")

    # 按规则拆分
    splitted = split_subtitles(srt_data)

    # 调用 GPT
    from openai import OpenAI
    client = OpenAI(
        api_key="sk-qTbd1AR4oMuP71ziRngmk3i0djrWVfLtuisvYKCH5B9jLz9g",
        base_url="https://api.chatanywhere.tech/v1")
    
    for chunk in splitted:
        # 将chunk拼接为文本
        chunk_text = '\n'.join([item[3] for item in chunk])
        result = call_gpt4o_mini_for_segment(chunk_text, client)
        print(result)