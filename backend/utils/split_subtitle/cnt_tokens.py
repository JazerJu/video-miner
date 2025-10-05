# 数整个段落中有多少个词。
import re
import re
from spellchecker import SpellChecker  # 或使用 nltk.corpus.words

def count_words(text: str) -> int:
    """
    统计混合文本内英文单词数、中文字符数、日文字符数和韩文字符数的总和
    优化版本：不使用SpellChecker，直接统计所有字母组合为单词
    """
    # 统计CJK字符（每个字符算1个词）
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u31f0-\u31ff]', text))
    korean_chars = len(re.findall(r'[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]', text))

    # 移除CJK字符后统计英文单词
    english_text = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\u31f0-\u31ff\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]', ' ', text)

    # 提取所有英文单词（2个字母以上，避免单字母噪声）
    words = re.findall(r'\b[a-zA-Z]{2,}\b', english_text.lower())
    english_words = len(words)

    total = english_words + chinese_chars + japanese_chars + korean_chars
    return total

def is_cjk_char(char):
    """判断字符是否为CJK字符（中文、日文、韩文）"""
    if not char:
        return False
    
    code_point = ord(char)
    # CJK Unified Ideographs
    if 0x4E00 <= code_point <= 0x9FFF:
        return True
    # CJK Extension A
    if 0x3400 <= code_point <= 0x4DBF:
        return True
    # Hiragana
    if 0x3040 <= code_point <= 0x309F:
        return True
    # Katakana
    if 0x30A0 <= code_point <= 0x30FF:
        return True
    # Hangul Syllables
    if 0xAC00 <= code_point <= 0xD7AF:
        return True
    # Hangul Jamo
    if 0x1100 <= code_point <= 0x11FF:
        return True
    
    return False

def is_english_char(char):
    """判断字符是否为英文字母"""
    return char.isalpha() and ord(char) < 128

def is_english_punctuation(char):
    """判断字符是否为英文标点符号"""
    english_punct = ".,;:!?\"'()[]{}/-_+=*&^%$#@~`|\\<>"
    return char in english_punct

def is_digit(char):
    """判断字符是否为数字"""
    return char.isdigit()

def get_char_display_width(char):
    """获取单个字符的display宽度"""
    if is_cjk_char(char):
        return 1.75
    elif is_english_char(char) or is_digit(char):
        return 1.0
    elif char == ' ' or is_english_punctuation(char):
        return 0.5
    else:
        # 其他字符默认按英文处理
        return 1.0

def cnt_display_words(text: str) -> float:
    """
    基于display宽度统计文本长度
    中文/日文/韩文: 1.75格, 英文/数字: 1格, 空格/标点: 0.5格
    """
    if not text:
        return 0.0
        
    # 将文本按token分割，这里简化处理，按空格分割
    tokens = text.split()
    total_width = 0.0
    
    for i, token in enumerate(tokens):
        # 计算token本身的宽度
        for char in token:
            total_width += get_char_display_width(char)
        
        # 判断是否需要在token后添加空格
        if i < len(tokens) - 1:  # 不是最后一个token
            if token:  # token不为空
                last_char = token[-1]
                # 如果以英文、数字或英文标点结尾，添加空格
                if is_english_char(last_char) or is_digit(last_char) or is_english_punctuation(last_char):
                    total_width += 0.5  # 空格占0.5格
    
    return total_width