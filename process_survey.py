#!/usr/bin/env python

VERSION = "0.2.0"

import re, random, sys, itertools, string, csv, os, difflib, subprocess
import numpy as np

######################################################################
######################################################################
# Configuration

FILENAME_PREFIX = "tam251_"

N_a = 5 # maximum number of answers per question
LAST_SCANTRON_QUESTION_NUMBER = 96

######################################################################
######################################################################
# Filenames

# input filenames
LIBRARY_FILENAME = FILENAME_PREFIX + "library.tex"
SCANTRON_FILENAME = FILENAME_PREFIX + "scantron.dat"

# output filenames
ANSWERS_FILENAME = FILENAME_PREFIX + "answers.csv"
REPORT_FILENAME = FILENAME_PREFIX + "report.tex"
RAW_STATS_PREFIX = FILENAME_PREFIX + "stats"

# logging filenames
LOG_PROC_REPORT_FILENAME = FILENAME_PREFIX + "proc_report.log"

# plot style
PLOT_STYLE = "bar"

######################################################################
######################################################################

def main():
    if len(sys.argv) != 2:
        print("process_questions version %s" % VERSION)
        print("")
        print("usage: process_questions <command>")
        print("")
        print("<command> is:")
        print("   proc-report    process the question and generate report")
        sys.exit(0)

    if sys.argv[1] == "proc-report":
        init_logging(LOG_PROC_REPORT_FILENAME)
        log_and_print("process_questions version %s" % VERSION)
        library = read_library(LIBRARY_FILENAME)
        N_q = sum([len(zone.questions) for zone in library.zones])
        (t, a) = read_scantrons(SCANTRON_FILENAME, N_q)
        write_answers(ANSWERS_FILENAME, library, t, a, N_a)
        d = generate_statistics(RAW_STATS_PREFIX, t, a, N_a)
        write_statistics(REPORT_FILENAME, library, d)
    else:
        print("ERROR: unrecognized command: %s" % sys.argv[1])
        print("valid commands are \"proc-report\"")
        sys.exit(1)

######################################################################
######################################################################

log_file = None

def init_logging(output_filename):
    global log_file
    try:
        print("Logging information to file: %s" % output_filename)
        if log_file != None:
            raise Exception("logging already initialized")
        log_file = open(output_filename, "w")
    except Exception as e:
        print("ERROR: failed to initialize logging: %s" % e)
        sys.exit(1)

def log(msg):
    global log_file
    try:
        if log_file == None:
            raise Exception("logging not initialized")
        log_file.write(msg + "\n")
    except Exception as e:
        print("ERROR: logging failed for message '%s': %s" % (msg, e))
        sys.exit(1)

def log_and_print(msg):
    log(msg)
    print(msg)

def die(msg):
    log_and_print(msg)
    sys.exit(1)

def log_array(arr, arr_name, dim_names):
    if len(arr.shape) != len(dim_names):
        die("log_array length mismatch for %s" % arr_name)
    log("%s array: (%s)"
        % (arr_name, ", ".join(["%s = %d" % (dim_names[i], arr.shape[i])
                                for i in range(len(arr.shape))])))
    log(np.array_str(arr))

######################################################################
######################################################################

class Struct(object):
    """Generic structure object.
    """
    def __init__(self):
        pass

######################################################################
######################################################################

class Library:
    """Data contained in the library.tex file.
    """
    def __init__(self):
        self.title_block = ""
        self.zones = []

class Zone:
    def __init__(self):
        self.title = ""
        self.questions = []

class Question:
    def __init__(self):
        self.body = ""
        self.left_choice = ""
        self.right_choice = ""

class LibraryRegexp:
    """A regexp for parsing library.tex.

    name is used to specify which rule matched
    regexp is the actual regular expression for the line
    no_tail indicates whether trailing text after the regexp is permitted
    """
    def __init__(self, name, regexp, no_tail=False):
        self.name = name
        self.regexp = regexp
        self.no_tail = no_tail

class ReadState:
    """The current state in the state machine used to parse library.tex.

    name is the state name

    zone, question, variant, and answer are the current objects of the
    relevant type. These are added to as new lines are read from the
    file.
    """
    def __init__(self):
        self.name = "preamble"
        self.zone = Zone()
        self.question = Question()

######################################################################
######################################################################

def ind2chr(index):
    """c = ind2chr(i)

    Convert the index i to a character c, so that 0 -> 'A', 1 -> 'B',
    etc. Invalid indexes convert to the character '*'.
    """
    index = int(index)
    if index < 0 or index >= len(string.ascii_uppercase):
        return "*"
    return string.ascii_uppercase[index]

def chr2ind(char):
    """i = ind2chr(c)

    Convert the character c to an index i, so that 'A' -> 0, 'B' -> 1,
    etc. Uppercase and lowercase are both converted. Invalid
    characters convert to -1.
    """
    if char in string.ascii_uppercase:
        return string.ascii_uppercase.index(char)
    if char in string.ascii_lowercase:
        return string.ascii_lowercase.index(char)
    return -1

######################################################################
######################################################################

def read_library(input_filename):
    """library = read_library(input_filename)

    Reads the library.tex file and returns a tree of
    Library()/Zone()/Question()/Variant()/Answer() objects.
    """
    log_and_print("Reading library file: %s" % input_filename)
    try:
        input_file = open(input_filename, "r")
    except Exception as e:
        die("ERROR: Unable to open library file for reading: %s: %s" % (input_filename, e))
    library_regexps = [
        LibraryRegexp(name="begin_document", regexp=r"^\s*\\begin\{document\}(?P<tail>.*)$", no_tail=True),
        LibraryRegexp(name="begin_zone", regexp=r"^\s*\\begin\{zone\}\{(?P<title>[^}]+)\}(?P<tail>.*)$", no_tail=True),
        LibraryRegexp(name="question", regexp=r"^\s*\\question\{(?P<body>.*)\}\{(?P<left_choice>[^}]*)\}\{(?P<right_choice>[^}]*)\}(?P<tail>.*)$", no_tail=True),
        LibraryRegexp(name="end_zone", regexp=r"^\s*\\end\{zone\}(?P<tail>.*)$", no_tail=True),
        LibraryRegexp(name="end_document", regexp=r"^\s*\\end\{document\}(?P<tail>.*)$", no_tail=True),
        LibraryRegexp(name="text", regexp=r"^.*\S.*$"),
        LibraryRegexp(name="blank", regexp=r"^\s*$"),
        ]
    library = Library()
    state = ReadState()
    for (i_line, line) in enumerate(input_file):
        def file_log(msg):
            log("%s:%d: %s" % (input_filename, i_line + 1, msg))
        def file_die(msg):
            die("%s:%d: ERROR: %s" % (input_filename, i_line + 1, msg))
        line = line.strip()
        file_log("read line: \"%s\"" % line)
            
        match_comment = re.search(r"(?<!\\)%", line)
        if match_comment:
            line = line[:match_comment.start()]
            file_log("stripped comments: \"%s\"" % line)
        match_name = None
        match = None
        for library_regexp in library_regexps:
            match = re.match(library_regexp.regexp, line)
            if match:
                match_name = library_regexp.name
                if library_regexp.no_tail:
                    extra_text = match.group("tail").strip()
                    if len(extra_text) > 0:
                        file_die("invalid extra text following '%s': %s" % (match_name, extra_text))
                break
        else:
            file_die("no matches found for line")
        file_log("found match '%s'" % match_name)

        def transition(new_state_name):
            file_log(r"state transition: '%s' -> '%s'" % (state.name, new_state_name))
            state.name = new_state_name
        def bad_transition():
            file_die("'%s' not allowed in state '%s'" % (match_name, state.name))
        def new_zone():
            file_log("starting new zone")
            state.zone = Zone()
            library.zones.append(state.zone)
            state.zone.title = match.group("title").strip()
        def new_question():
            file_log("starting new question")
            state.question = Question()
            state.zone.questions.append(state.question)
            state.question.body = match.group("body").strip()
            state.question.left_choice = match.group("left_choice").strip()
            state.question.right_choice = match.group("right_choice").strip()
        def append_to_title_block():
            file_log("appending line to title block")
            if len(library.title_block) > 0:
                library.title_block += "\n"
            library.title_block += line

        if state.name == "preamble":
            if match_name == "begin_document":   transition("title_block")
            elif match_name == "text":           file_log("skipping text line")
            elif match_name == "blank":          file_log("skipping blank line")
            else: bad_transition()
        elif state.name == "title_block":
            if match_name == "text":             append_to_title_block()
            elif match_name == "blank":          append_to_title_block()
            elif match_name == "begin_zone":     transition("zone"); new_zone()
            else: bad_transition()
        elif state.name == "zone":
            if match_name == "blank":            pass
            elif match_name == "text":           file_log("skipping text line")
            elif match_name == "question":       new_question()
            elif match_name == "end_zone":       transition("between_zones")
            else: bad_transition()
        elif state.name == "between_zones":
            if match_name == "blank":            pass
            elif match_name == "text":             pass
            elif match_name == "begin_zone":     transition("zone"); new_zone()
            elif match_name == "end_document":   file_log("stopping file reading"); break
            else: bad_transition()
        else:
            file_die("unknown state '%s'" % state.name)

    input_file.close()
    log("Successfully completed library reading")
    return library

######################################################################
######################################################################

def read_scantrons(input_filename, N_q):
    """(t, a) = read_scantrons(input_filename, N_q)

    Read the scantron data arrays from scantron.dat.

    t[s] = TA number for student s
    a[s,q] = answer given by student s to question q
    """
    log_and_print("Reading Scantron file: %s" % input_filename)
    t_data = []
    a_data = []
    with open(input_filename, "r") as in_f:
        for (i_line, line) in enumerate(in_f):
            def check_match(s, pattern, offset, field, min_length, strip):
                if strip:
                    s = s.strip()
                cleaned_s = re.sub(pattern, " ", s)
                if strip:
                    cleaned_s = cleaned_s.strip()
                if len(s) == 0 and min_length > 0:
                    log_and_print("%s:%s: WARNING: field '%s' at character %d is empty"
                                  % (input_filename, i_line + 1, field, offset + 1))
                    return cleaned_s
                if len(s) < min_length:
                    log_and_print("%s:%s: WARNING: field '%s' at character %d has length %d but should be at least %d: %s"
                                  % (input_filename, i_line + 1, field, offset + 1, len(s), min_length, s))
                    return cleaned_s
                bad_chars = False
                for match in re.finditer(pattern, s):
                    bad_chars = True
                    i = match.start()
                    log_and_print("%s:%s: WARNING: invalid character '%s' at character %d at position %d in field '%s': %s"
                                  % (input_filename, i_line + 1, s[i], i + offset + 1, i + 1, field, s))
                if bad_chars:
                    return cleaned_s
                return s

            if len(line) == 1 and ord(line[0]) == 26:
                # last line has a single char
                continue

            line_end = 72 + LAST_SCANTRON_QUESTION_NUMBER

            if len(line) < line_end:
                die("%s:%d: ERROR: line length %d less than expected %d" \
                        % (input_filename, i_line + 1, len(line), line_end))

            section = check_match(line[60:63], "[^0-9]", 60, "Section", 3, True)
            answers = check_match(line[72:72 + N_q], "[^0-9 ]", 72, "Answers", 0, False)

            answers = ["*" if c == " " else ind2chr(int(c) - 1)
                       for c in answers]
            log("%s:%s: section %s"
                % (input_filename, i_line + 1, section))

            t_data.append(section)
            a_data.append(list(answers))

    t = np.array(t_data, dtype=object)
    a = np.array(a_data, dtype=str)
    log_array(a, "a", ["N_s", "N_q"])
    log("Successfully completed reading Scantron file")
    return (t, a)

######################################################################
######################################################################

def write_answers(output_filename, library, t, a, N_a):
    """write_answers(output_filename, library, t, a, N_a)

    Write per-student answers to the answers.csv file.
    """
    log_and_print("Writing answers CSV file: %s" % output_filename)
    (N_s, N_q) = a.shape
    with open(output_filename, "w") as out_f:
        qi = 0
        for zone in library.zones:
            for question in zone.questions:
                if qi > 0:
                    out_f.write(",")
                out_f.write('"%d. %s"' % (qi + 1, question.body))
                qi += 1
        out_f.write('\n')
        
        for si in range(N_s):
            for qi in range(N_q):
                if qi > 0:
                    out_f.write(",")
                ai = chr2ind(a[si,qi])
                if ai >= 0:
                    out_f.write("%d" % ai)
            out_f.write('\n')
    log("Successfully completed writing answers CSV file")

######################################################################
######################################################################

def write_csv(output_filename, headers, data, index_formats=None):
    """Write the given array as a CSV file.

    For 1D data there should be two headers, index and value. For nD
    data there should be n headers, with the last header containing a
    %d conversion character.

    An nD array is written with the first n - 1 indexes as rows, and
    the last index as the columns. Breaking this rule, a 1D array is
    written as a column.
    """
    log_and_print("Writing statistics file: %s" % output_filename)
    if index_formats == None:
        index_formats = ["i"] * len(data.shape)
    def format_index(i, f):
        if f == "i":
            return i + 1
        elif f == "c":
            return ind2chr(i)
    with open(output_filename, "w") as out_f:
        writer = csv.writer(out_f)
        if len(data.shape) == 0:
            writer.writerow(headers[0])
            writer.writerow([data])
        elif len(data.shape) == 1:
            assert(len(headers) == 2)
            writer.writerow(headers)
            for i in range(data.shape[0]):
                writer.writerow([format_index(i, index_formats[0]), data[i]])
        else:
            row = headers[:-1]
            for j in range(data.shape[-1]):
                row.append(headers[-1] % format_index(j, index_formats[-1]))
            writer.writerow(row)
            for index in np.ndindex(data.shape[:-1]):
                row = [format_index(index[i], index_formats[i])
                           for i in range(len(index))]
                for j in range(data.shape[-1]):
                    row.append(data[index + (j,)])
                writer.writerow(row)
    log("Successfully completed writing statistics file")

def generate_statistics(output_prefix, t, a, N_a):
    """d = generate_statistics(output_prefix, t, a, N_a)

    d is a structure containing all data arrays and all generated
    statistics arrays.

    Statistics arrays are output to individual files with the given
    output_prefix.
    """
    log_and_print("Generating statistics")
    d = Struct()

    (d.N_s, d.N_q) = a.shape
    d.N_a = N_a

    d.t = t
    d.a = a

    d.n_s_qa = np.zeros((d.N_q, d.N_a), dtype=int)
    for si in range(d.N_s):
        for qi in range(d.N_q):
            ai = chr2ind(d.a[si,qi])
            if ai >= 0:
                d.n_s_qa[qi,ai] += 1
    write_csv(output_prefix + "_n_s_qa.csv", ["q", "n_s(q,a=%s)"], d.n_s_qa,
              index_formats=['i', 'c'])

    d.n_s_q = d.n_s_qa.sum(axis=1)
    write_csv(output_prefix + "_n_s_q.csv", ["q", "n_s(q)"], d.n_s_q)

    d.n_na_q = d.N_s - d.n_s_q
    write_csv(output_prefix + "_n_na_q.csv", ["q", "n_na(q)"], d.n_na_q)

    d.p_q = np.zeros(d.N_q, dtype=float)
    for qi in range(d.N_q):
        for ai in range(d.N_a):
            d.p_q += (ai + 1) * float(d.n_s_qa[qi,ai]) / d.n_s_q[qi]
    write_csv(output_prefix + "_p_q.csv", ["q", "p(q)"], d.p_q)

    d.r_s_qa = np.zeros((d.N_q, d.N_a), dtype=float)
    for qi in range(d.N_q):
        for ai in range(d.N_a):
            d.r_s_qa[qi,ai] = float(d.n_s_qa[qi,ai]) / d.N_s
    write_csv(output_prefix + "_r_s_qa.csv", ["q", "r_s(q,a=%s)"], d.r_s_qa,
              index_formats=['i', 'c'])

    d.r_na_q = np.zeros(d.N_q, dtype=float)
    for qi in range(d.N_q):
        d.r_na_q[qi] = float(d.n_na_q[qi]) / d.N_s
    write_csv(output_prefix + "_r_na_q.csv", ["q", "r_na(q)"], d.r_na_q)

    log("Successfully completed generating statistics")
    return d

######################################################################
######################################################################

def write_stats_tex_question_answers_left_right(out_f, library, d):
    qi = 0
    for zone in library.zones:
        out_f.write(r"\paragraph{%s}\ \\[-1.5em]" % zone.title + "\n")
        out_f.write(r"\begin{longtable}{p{8cm}p{2cm}cl}" + "\n")
        width = 5
        for question in zone.questions:
            out_f.write("%d. %s" % (qi + 1, question.body) + "\n")
            out_f.write(r"& \raggedleft {\scriptsize %s}" % question.left_choice + "\n")

            out_f.write(r"&" + "\n")
            out_f.write(r"\hspace*{-1.5em}" + "\n")
            out_f.write(r"\begin{tikzpicture}[baseline=0.3em]" + "\n")
            out_f.write(r"\begin{axis}[" + "\n")
            out_f.write(r"xbar stacked," + "\n")
            out_f.write(r"bar width=2mm," + "\n")
            out_f.write(r"ymin=0,ymax=2," + "\n")
            out_f.write(r"xmin=-100,xmax=100," + "\n")
            out_f.write(r"xtick={-100,-50,50,100}," + "\n")
            out_f.write(r"minor xtick={-75,-25,25,75}," + "\n")
            out_f.write(r"extra x ticks={0}," + "\n")
            out_f.write(r"extra x tick style={grid=major}," + "\n")
            out_f.write(r"xticklabels={}," + "\n")
            out_f.write(r"ytick=\empty," + "\n")

            out_f.write(r"width=%gcm, height=2cm," % width + "\n")
            out_f.write(r"]" + "\n")
            offset = sum([d.r_s_qa[qi,ai] for ai in range(d.N_a) if ai < d.N_a / 2])
            out_f.write(r"\addplot+[xbar,draw=none,fill=none] plot coordinates {" + "\n")
            out_f.write(r"(%g,1)" % (-offset * 100) + "\n")
            out_f.write(r"};" + "\n")
            colors = [
                "blue,fill=blue!30!white",
                "blue,fill=blue!10!white",
                "black,fill=white",
                "red,fill=red!10!white",
                "red,fill=red!30!white",
                ]
            for ai in range(d.N_a):
                if d.N_a % 2 == 1 and ai == d.N_a / 2:
                    continue
                out_f.write(r"\addplot+[xbar,%s] plot coordinates {" % colors[ai] + "\n")
                out_f.write(r"(%g,1)" % (d.r_s_qa[qi,ai] * 100) + "\n")
                out_f.write(r"};" + "\n")
            out_f.write(r"\end{axis}" + "\n")
            out_f.write(r"\end{tikzpicture}" + "\n")
            out_f.write(r"\hspace*{-1.5em}" + "\n")

            out_f.write(r"& {\scriptsize %s} \\" % question.right_choice + "\n")
            
            qi += 1

        out_f.write(r"\end{longtable}" + "\n")

def write_stats_tex_question_answers(out_f, library, d):
    qi = 0
    width = 5
    for zone in library.zones:
        out_f.write(r"\vspace{2em}" + "\n")
        out_f.write(r"\subsection*{%s}\ \\[-1.5em]" % zone.title + "\n")
        out_f.write(r"\vspace{-2em}" + "\n")
        out_f.write(r"\begin{longtable}{p{7.5cm}p{2cm}cp{2cm}}" + "\n")
        out_f.write(r"\hline\\[0.2em]" + "\n")
        for question in zone.questions:
            out_f.write(r"\parbox[b]{\hsize}{\raggedright %d. %s}" % (qi + 1, question.body) + "\n")
            out_f.write(r"& \parbox[b]{\hsize}{\raggedleft \scriptsize %s}" % question.left_choice + "\n")
            out_f.write(r"&" + "\n")
            out_f.write(r"\hspace*{-1.3em}" + "\n")
            if PLOT_STYLE == "bar":
                out_f.write(r"\begin{tikzpicture}[baseline]" + "\n")
                out_f.write(r"\begin{axis}[" + "\n")
                out_f.write(r"title={\scriptsize N = %d}," % d.n_s_q[qi] + "\n")
                out_f.write(r"every axis title shift=0pt," + "\n")
                out_f.write(r"ybar, ymin=0," + "\n")
                out_f.write(r"width=%gcm, height=2.5cm," % width + "\n")
                #out_f.write(r"symbolic x coords={A,B,C,D,E,none}," + "\n")
                out_f.write(r"symbolic x coords={A,B,C,D,E}," + "\n")
                out_f.write(r"xtick=data," + "\n")
                out_f.write(r"enlarge x limits=0.12," + "\n")
                out_f.write(r"xticklabel style={font=\scriptsize}," + "\n")
                out_f.write(r"yticklabel style={font=\scriptsize}," + "\n")
                out_f.write(r"xtick pos=left," + "\n")
                #out_f.write(r"bar width=%gcm," % (width / float(d.N_a + 1) / 2) + "\n")
                out_f.write(r"bar width=%gcm," % (width / float(d.N_a) / 2) + "\n")
                out_f.write(r"]" + "\n")
                out_f.write(r"\addplot coordinates {" + "\n")
                for ai in range(d.N_a):
                    #out_f.write(r"(%s,%g)" % (ind2chr(ai), d.r_s_qa[qi,ai] * 100) + "\n")
                    value = d.r_s_qa[qi,ai] / d.r_s_qa[qi,:].sum() * 100
                    label = ind2chr(ai)
                    out_f.write(r"(%s,%g)" % (label, value) + "\n")
                #out_f.write(r"(none,%g) [0]" % (d.r_na_q[qi] * 100) + "\n")
                out_f.write(r"};" + "\n")
                out_f.write(r"\end{axis}" + "\n")
                out_f.write(r"\end{tikzpicture}" + "\n")
            elif PLOT_STYLE == "stacked":
                out_f.write(r"\begin{tikzpicture}[baseline]" + "\n")
                out_f.write(r"\begin{axis}[" + "\n")
                out_f.write(r"title={\scriptsize N = %d}," % d.n_s_q[qi] + "\n")
                out_f.write(r"every axis title shift=0pt," + "\n")
                out_f.write(r"width=%gcm,height=2.1cm," % width + "\n")
                out_f.write(r"xbar stacked," + "\n")
                out_f.write(r"ytick=\empty," + "\n")
                out_f.write(r"xmin=0, xmax=100," + "\n")
                out_f.write(r"xtick={0,25,50,75,100}," + "\n")
                out_f.write(r"xticklabel style={font=\scriptsize}," + "\n")
                out_f.write(r"nodes near coords," + "\n")
                out_f.write(r"point meta=explicit symbolic," + "\n")
                out_f.write(r"cycle list={{fill=blue!50!white,font={\tiny}},{fill=blue!20!white,font={\tiny}},{fill=black!10!white,font={\tiny}},{fill=red!20!white,font={\tiny}},{fill=red!50!white,font={\tiny}}}," + "\n")
                out_f.write(r"]" + "\n")
                for ai in range(d.N_a):
                    # slightly shorten to fix bug where labels aren't rendered if total is slightly more than 100
                    value = d.r_s_qa[qi,ai] / d.r_s_qa[qi,:].sum() * 100 * 0.999
                    label = ind2chr(ai) if value > 7 else ""
                    out_f.write(r"\addplot coordinates {" + "\n")
                    out_f.write(r"(%g,1) [%s]" % (value, label) + "\n")
                    out_f.write(r"};" + "\n")
                out_f.write(r"\end{axis}" + "\n")
                out_f.write(r"\end{tikzpicture}" + "\n")
            else:
                raise Exception("unknown PLOT_STYLE: " + PLOT_STYLE)
            out_f.write(r"\hspace*{-1em}" + "\n")
            out_f.write(r"& \parbox[b]{\hsize}{\raggedright \scriptsize %s} \\[1.1em]" % question.right_choice + "\n")
            out_f.write(r"\hline\\[0.2em]" + "\n")

            qi += 1

        out_f.write(r"\end{longtable}" + "\n")

def write_statistics(output_filename, library, d):
    """write_statistics(output_filename, library, d)

    Write summary statistics to the stats.tex file.
    """
    log_and_print("Writing statistics tex file: %s" % output_filename)
    with open(output_filename, "w") as out_f:
        out_f.write(r"\documentclass{article}" + "\n")
        out_f.write(r"\usepackage[margin=2.5cm]{geometry}" + "\n")
        out_f.write(r"\usepackage{pgfplots}" + "\n")
        out_f.write(r"\pgfplotsset{compat=1.10}" + "\n")
        out_f.write(r"\usepackage{longtable}" + "\n")
        out_f.write(r"\begin{document}" + "\n")
        out_f.write("\n")
        out_f.write(r"%s" % library.title_block + "\n")
        out_f.write("\n")

        #write_stats_tex_question_answers_left_right(out_f, library, d)
        #out_f.write(r"\newpage" + "\n")
        #out_f.write(r"\centerline{\Large \bf Detailed response breakdown}" + "\n")
        write_stats_tex_question_answers(out_f, library, d)

        out_f.write(r"\end{document}" + "\n")
    log("Successfully completed writing statistics tex file")

######################################################################
######################################################################

if __name__ == "__main__":
    main()
