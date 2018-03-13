# `process_survey.py`

This is a script to do surveys using scantrons. It is used for
Informal Early Feedback (IEF) surveys in the TAM 2XX courses at UIUC.


## Question LaTeX library file

1. Copy [example_library.tex] and rename it for the appropriate course, e.g., `tam212_sp18_library.tex`.

2. Edit the questions, organizing them into groups with `\begin{zone}...\end{zone}` and using the special command `\question{TEXT}{LEFT_ANSWER}{RIGHT_ANSWER}` for each question. It is important to use these commands exactly as in the same was as in the example file, so that the script can process it correctly later.


## Running the survey

1. Latex the library file and print copies for each student:
```
pdflatex tam212_sp18_library.tex
```

2. Give each student a printed question page and a blank Scantron form.

3. Students complete the multiple-choice survey questions on the Scantron form, and fill out the written free-response questions on the question form.

4. Collect the Scantron forms together, and separately collect any question pages with written free-response answers. The free-response answers can be processed manually.


## Process the Scantrons

1. Take the Scantrons to the scanning facility. Request that the forms be scanned and the "raw .dat file" sent back by email.

2. Get the scanned data file (named something like `jd26936.dat` and rename it to `tam212_sp18_scantron.dat`. It is important that this file has exactly the same prefix as the library file.


## Process the survey

1. Make a directory that contains:
```
tam212_sp18_library.tex
tam212_sp18_scantron.dat
process_survey.py
```

2. Edit `process_survey.py` and set `FILENAME_PREFIX=tam212_sp18_` (or whatever your course prefix is).

3. Run:
```
python process_survey.py
```

4. Generate the survey PDF:
```
pdflatex tam212_sp18_report.tex
```
This generates the file `tam212_sp18_report.pdf`.


## Optional: get the CSV data

As well as the report PDF generated above, there are also CSV files generated with the processed data in them:

```
tam212_sp18_stats_n_na_q.csv   # number of non-responses per question
tam212_sp18_stats_n_s_q.csv    # number of responses per question
tam212_sp18_stats_n_s_qa.csv   # number of responses per question per answer
tam212_sp18_stats_p_q.csv      # average response per question (1 = A, 5 = E)
tam212_sp18_stats_r_na_q.csv   # fraction of responses per question per answer
tam212_sp18_stats_r_s_qa.csv   # fraction of non-responses per question
```


## Optional: filter by the answer to a specfic question

Question 1 in the example library is "Who is your professor?" with options A and B for the two professors. If we want to generate survey statistics for only one of the professors then we can run:
```
python -q 1 -a A process_survey.py
```
This generates output that only includes Scantrons where the answer to Question 1 was A.
