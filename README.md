# Finding Nemo

A century ago, people went to the priest for guidance in their lives. Today, we turn to the chatbot. But who is it that we ask? What underlying ideology generates the advice that this sage provides? The goal of **Finding Nemo** is to find out.

We approximated the ideological positions of four popular AI models — **gpt-4o**, **claude-sonnet-4-5**, **gemini-2.5-flash**, and **grok-4**. In an attempt to elicit their beliefs, we transformed 50 questions sourced from five online political-values quizzes into first-person narratives that the AI models would actually participate in. With answers in hand, we determined how closely they aligned with the views of eight prominent political figures spanning the ideological spectrum. We used Claude instances as judges, providing each with documents that represent a public record of its figure and instructing it to grade responses by only referencing what the figure said — rather than the judge's own priors. We projected each AI model onto a political compass using a weighted-centroid model of the response scores. The result is a picture of where the four models sit relative to one another and to well-known political figures.

## Inspiration

Frontier AI labs have generally attempted to make their products politically neutral. However, it can be difficult to verify this: asking current AIs for direct values on political topics often results in responses such as *"I'd rather lay out the landscape than push my own take"*. The community should be able to easily verify the political stances of AI models rather than just take the word of AI labs. The political stances of current AIs may influence user ideologies, and if undetected, may transfer to future AIs. Actual political stances differing from developer- (AI lab–) perceived stances is an alignment problem.

## What it does

What if we took an indirect approach: asking AIs to help with scenarios based on political questions, using LLM judges to evaluate similarity to what famous political figures might do in those scenarios, and then estimating a political-compass position based on figure-affinity scores — comparing those coordinates to the `(0, 0)` coordinate treated as neutral?

## How we built it

Four team members collaborated on design and execution. AI responses came through API calls to AI-lab servers and were stored in Snowflake. The judges were RAG-assisted, political-figure-prompted Opus 4.7 instances.

## Challenges we ran into

- **Scoping.** We originally wanted to see how well AIs could emulate specific thinker ideology, but ran out of time.
- **Eight dimensions to two.** Taking eight political-thinker affinity scores per AI agent and converting those to compass coordinates was more difficult than anticipated. Information was lost going from eight dimensions to two, and we spent significant effort minimizing that loss.

## Accomplishments that we're proud of

Building this project. Learning about different methods of measuring AI political ideology, contrasting our method to them, and contextualizing our results against the claims made by major AI labs.

## What we learned

First hackathon for some members of our group: time management, collaboration, and just the general vibe were great learning experiences — discussing the idea, quickly implementing, deciding which tools and platforms to use and how, and incorporating peer feedback.

AI-safety specific: it is difficult to accurately measure AI-model political ideology with a high degree of confidence. We also learned more about the relevance of AI-model political ideology by thinking about what types of user conversations might be influenced by differing ideologies, and the importance of users being aware of these potential biases.

## What's next for Finding Nemo

Hopefully we can expand this project. There are a lot of areas for future work — e.g., more political figures as reference points / anchors, and multiple judges backed by different AIs.

## Built With

- **Models:** Claude, ChatGPT, Gemini, Grok
- **Audio generation:** ElevenLabs
- **Data storage:** Snowflake
- **Language:** Python

## Try it out

- GitHub repo: <https://github.com/wwmuchi/Nemo>
- Live demo: <https://matt-reviewed-literally-bye.trycloudflare.com>
- Slides: <https://docs.google.com>
- Demo video: <https://www.youtube.com/watch?v=0lYth1a_q84>
