"""
视频分割提示信息
"""

VIDEO_SPLIT_PROMPT_TEMPLATE = """
## Role
You are a professional Netflix subtitle splitter expert who specializes in segmenting continuous text into sentence fragments separated by <br> tags.

## Segmentation Rules 
1. Length limits

* Chinese/Japanese/Korean: each segment ≤ 12 characters;
* English: each segment ≤ 20 words, target 14-18 words; unless there is strong punctuation (. ? ! ; :) or a timestamp, **do not make an English segment shorter than 8 words**.

2. Only insert `<br>` between segments; **do not change any character of the original text** (including spaces, casing, punctuation, timestamps).

3. English break priority & strategy (backtrack to the **last eligible break** in this order):

* Prefer to break **before** these connectives/relatives (not after):
  and, but, so, because, although, however, therefore, since, that, which, who, whose, whom, when, where
* If there is a copula/auxiliary, **you may break after it** (e.g., is/are/was/were/be/been/am/has/have/had/will/would/can/could/should/must/may/might), but only when the current segment has reached the target range (≥ 14 words).
* If none of the above apply and the segment would exceed the limit, choose the **space nearest to the 20-word cap** without exceeding it.

4. English “do-not-break” positions (must not break here):

* Determiner/adjective + noun (a/an/the/this/that/these/those + N; or adjective + noun).
* Preposition + object (of/in/on/at/for/to/with/from/by … + noun phrase).
* Verb + particle in phrasal verbs (pick up, set up, look for, come up with, etc.).
* “to + verb” (do not break immediately after “to”).
* **Before** relative/subordinating words (that/which/when/where, etc.); if needed, break **after** them.
* If punctuation would create an English segment < 8 words and no strong punctuation forces a break, merge with the following text until the next natural breakpoint.

5. Punctuation & timestamps

* Strong punctuation (. ? ! ; :) are natural breakpoints; if a break there makes the English segment < 8 words and no other rule is violated, you may merge forward to the next preferred breakpoint.
* Timestamps (e.g., `00:10`) and the text immediately following belong to the **same segment start**; never isolate a timestamp as its own segment.

6. CJK segmentation

* Segment by semantics, preferably after function words or natural pauses; strictly enforce “≤ 12 characters per segment.”

7. Output

* Insert `<br>` **only** between segments; add no explanations or extra symbols.


## Given Text
<split_this_sentence>
{sentence}
</split_this_sentence>

## Output in only JSON format and no other text
{{
    "split": "splitted approach with <br> tags at split positions",
}}
"""

# Note: Start you answer with ```json and end with ```, do not add any other text.

# input:
# the upgraded claude sonnet is now available for all users developers can build with the computer use beta on the anthropic api amazon bedrock and google cloud’s vertex ai the new claude haiku will be released later this month
# output:
# the upgraded claude sonnet is now available for all users<br>developers can build with the computer use beta<br>on the anthropic api amazon bedrock and google cloud’s vertex ai<br>the new claude haiku will be released later this month

"""
电影级PROMPT,会完整地返回一个句子，甚至逗号都不分割，在平时的视频里显得“超长”，作为尝试中的废案保存在这里。
"""

"""
MOVIE_SPLIT_PROMPT_TEMPLATE = 
## Role
You are a professional Netflix subtitle splitter in **{language}**.

## Task
Split the given subtitle text into **{num_parts}** parts, each less than **{word_limit}** words.

1. Maintain sentence meaning coherence according to Netflix subtitle standards
2. MOST IMPORTANT: Keep parts roughly equal in length (minimum 3 words each)
3. Split at natural points like punctuation marks or conjunctions
4. If provided text is repeated words, simply split at the middle of the repeated words.

## Steps
1. Analyze the sentence structure, complexity, and key splitting challenges
2. Generate two alternative splitting approaches with [br] tags at split positions
3. Compare both approaches highlighting their strengths and weaknesses
4. Choose the best splitting approach

## Given Text
<split_this_sentence>
{sentence}
</split_this_sentence>

## Output in only JSON format and no other text
```json
{{
    "analysis": "Brief description of sentence structure, complexity, and key splitting challenges",
    "split1": "First splitting approach with <br> tags at split positions",
    "split2": "Alternative splitting approach with <br> tags at split positions",
    "assess": "Comparison of both approaches highlighting their strengths and weaknesses",
    "choice": "1 or 2"
}}
```
Note: Start you answer with ```json and end with ```, do not add any other text.
"""

"""
num_parts 的计算逻辑：

1. 获取 tokens 数量：

使用 count_words(sentence, nlp) 对句子进行分词
计算分词后的 token 总数：len(tokens)


2. 计算分割部分数：

用 token 总数除以每部分的最大长度：len(tokens) / max_length
使用 math.ceil() 向上取整，确保所有 tokens 都能被包含

句子的分词可以简单得用nltk或者正则表达式，
但VideoLingo用的是spacy，太重，尤其是我使用字级时间戳之后，其实并不需要太好的分词。
"""