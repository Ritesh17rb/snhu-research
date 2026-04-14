Regarding your work on embedumap, the primary task is to identify the top 10 universities whose research should be analyzed for additional research opportunities, with SNHU (Southern New Hampshire University) specifically named as one of the target institutions.1
Assigned Tasks for embedumap and SNHU
University Selection: You are to identify a list of 10 prominent universities. Beyond SNHU, the speaker suggested looking at organizations like Capital University and GC.23
Data Sourcing: For these universities, you must find research papers from sources such as Open Alex and arXiv.org.4
Visualization Requirements:
Create separate "embeds" for each university that visually represent their research fields.5
The visualization should distinguish between the university’s specific publications and the broader "full universe" of research.6
Reproduce a "strategy story" for each university to evaluate where they should focus future research to improve their reputation.7
Algorithm and Label Improvements:
Centroid Intent: Ensure the algorithm correctly picks up the intent of the "centroid time period" (e.g., if set to 4 years, it should group data into 4-year clusters).8
Timestamp Labels: Dynamic labels should use the shortest possible string to differentiate time periods (e.g., use "Year-Month" instead of "Year-Month-Day" if the day is not needed for distinction).9
Documentation: Move parameter-level details (like examples for centroid time periods) from the notes section of the readme.md to specific parameter descriptions.10
Meeting Transcript Excerpt (Relevant to Ritesh)
Anand S: "...Thank you for the Eric mapping. Um, this I ended up presenting a couple of times and it was good... a few changes on the embedmap... The whole point of specifying a centroid time period is that when I say four years, it should take everything for a four-year period like this and then say, 'Now for this bunch, there is a centroid. The next four years, there is another centroid... and so on.' So at least the number of points would have changed. That is not happening. So I'm guessing it's not picking up the intent of the algorithm."8

Anand S: "Second, the timestamp... It should be the shortest string that allows us to differentiate... Thirdly, that documentation can be improved a bit... readme.md... should have parameter-level details."911

Anand S: "Now there is another thing that I want to pass you. This is an embedding of the National Institute of Education... versus Open Alex papers... What I'd like you to do... My aim is to identify the top 10 list of universities whose research I should analyze to evaluate where there are potential additional research opportunities... SNHU is definitely one... For each of these universities, what I would like is a separate embed... and a strategy story for each."7