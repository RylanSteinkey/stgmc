import os, sys, io
import base64
import zipfile

import xml.etree.ElementTree as ET
from striprtf.striprtf import rtf_to_text
from collections import Counter
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

import seaborn as sns
import matplotlib.pyplot as plt

def find_all():
    """
    Returns of list of patient files
    """
    files = os.listdir("data/pts/")
    return files

def get_diagnosis(xml):
    """
    Takes the name of a patient xml file and returns a list of hospital admissions,
    the principal diagnosis of each admission, and the discharge date
    """
    reasons = []
    dates = []

    try:
        tree = ET.parse(xml)
        root = tree.getroot()
    except:
        print("Error reading XML {}, check for corruption".format(xml))
        return ['invalid'],[datetime(2024, 10, 4, 12, 0)]

    docs = root.findall('CorrespondenceIn/Document')
    for doc in docs:
        dcs = doc.findall('CATEGORY')
        for dc in dcs:
            if isinstance(dc.text, str):
                if dc.text.strip() == "Discharge Summary": # check for discharge date
                    rt = doc.find("DocumentPage/Content")
                    date = doc.find("CORRESPONDENCEDATE").text

                    # only look at the dcs in the last x days
                    search_period = 185
                    date_format = '%d/%m/%Y %H:%M:%S %p'
                    date_obj = datetime.strptime(date, date_format)

                    start_period = datetime.now() - timedelta(days = search_period)

                    # if this is true, then the discharge summary was from more than search_period days ago
                    if date_obj < start_period:
                        continue

                    dates.append(date_obj)

                    """
                    From here the files can be base64 encoded utf-8 rtf
                    which start with the prefix e1xyd
                    or base64 encoded zip archives
                    which start with the prefix UEsDB
                    or Bitmaps, jpegs, and pdfs, which we skip
                    """
                    if rt.text[:5] == 'e1xyd':
                        rt = base64.b64decode(rt.text)
                        rt = rt.decode('utf-8')

                    elif rt.text[:5] == "UEsDB":
                        rt = base64.b64decode(rt.text)
                        # convert to bytes for zipfile
                        brt = io.BytesIO(rt)
                        with zipfile.ZipFile(brt, 'r') as brt_zip:
                            try:
                                assert len(brt_zip.infolist()) == 1
                            except:
                                print("Too many files in zip for discharge summary {} on date {}".format(xml,date))
                                raise

                            try:
                                comp_file = brt_zip.infolist()[0]
                                with brt_zip.open(comp_file) as decomp_file:
                                    # this should read the file as bytes
                                    decomp_dcs = decomp_file.read()

                                    # check if pdf, maybe learn how to read these...
                                    if decomp_dcs[1:4] == b'PDF':
                                        print("skipping PDF discharge summary {} on date {}".format(xml,date))
                                        continue

                                    # also skip bitmaps cause no way
                                    elif decomp_dcs[:2] == b'BM':
                                        print("skipping Bitmap discharge summary {} on date {}".format(xml,date))
                                        continue

                                    # apparently some of these are JPEG'
                                    elif decomp_dcs[:2] == b'\xff\xd8':
                                        print("skipping JPEG discharge summary {} on date {}".format(xml,date))
                                        continue

                                    else:
                                    # This is now RTF
                                        rt = decomp_dcs.decode('utf-8')
                            except:
                                print("Unable to decode zipped file for discharge summary {} on date {}".format(xml,date))
                                raise


                    else:
                        raise Exception("Undeclared file header on discharge summary {} on date {}".format(xml,date))


                    # convert to rtf
                    rt = rtf_to_text(rt)

                    # extract diagnosis
                    prin = -1
                    for line_num, line in enumerate(rt.split('\n')):
                        if 'PRINCIPAL DIAGNOSIS' in line:
                            prin = line_num+2
                        if prin == line_num:
                            if ':' in line:
                                try:
                                    prin_diag = line.split(':')[1][1:]
                                except:
                                    print("unable to read diagnosis line: {}".format(line))
                                    raise
                            else:
                                prin_diag = line[2:]
                            reasons.append(prin_diag)
                            continue
                            # can do secondary diag if needed as well...
                            # NB most dont have 2ndary diag
                            # can check for previous medical history here
                            # i dont think there is futility in doing this...

    return reasons, dates

def get_conditions(xml):
    """
    Takes a single patient chart path
    returns a list of Active conditions according to their bppremier
    """
    conditions = []
    try:
        tree = ET.parse(xml)
        root = tree.getroot()
    except:
        print("Error reading XML {}, check for corruption".format(xml))
        return ['invalid']

    conds = root.findall('PastHistory/Condition')
    for cond in conds:
        is_active = int(cond.find('STATUSCODE').text)
        if is_active:
            conditions.append(cond.find('ITEMTEXT').text)

    return conditions

def get_visits(xml):
    """
    Takes a patient file (xml)
    returns all visits; the dates, and the internalID
    (to check for chronic care plan)
    """
    all_visits = []

    try:
        tree = ET.parse(xml)
        root = tree.getroot()
    except:
        print("Error reading XML {}, check for corruption".format(xml))
        return ['invalid']

    visits = root.findall("Visits/Visit")
    for visit in visits:
        id = visit.find('INTERNALID').text
        date = visit.find('VISITDATE').text

        if visit.find("DRNAME").text == "HotDoc External Vendor":
            continue

        date_format = '%d/%m/%Y %H:%M:%S %p'
        try:
            date_obj = datetime.strptime(date, date_format)
        except:
            print("Cant read time from visit from {}... continuing".format(xml))
            continue

        all_visits.append([date_obj,id])

    if len(all_visits) == 0:
        print("No visits found for patient {}".format(xml))

    return all_visits


def gather_info():
    """
    loads the classification xlsx and saves figures about it
    """
    df = pd.read_excel("dcs_classifications.xlsx")

    """
    All reasons pie chart
    """
    reasons = df['System']
    reasons_c = Counter(reasons)
    reas, counts = zip(*sorted(reasons_c.items(), key=lambda x: x[1], reverse=True))
    plt.figure(figsize=(8, 8))
    plt.pie(counts, labels=reas,autopct='%1.0f%%')
    plt.savefig("figures/all_reasons.png")
    plt.clf()

    """
    Is dcs chronic disease related pie chart
    """
    chron_prev = df['Chronic prev']
    chron_perc = np.sum(chron_prev)/len(chron_prev)*100
    vals = [chron_perc, 100-chron_perc]
    labels = ["Needed or\nWill Need\nManagement Plan","Presentation Unreleated\nto Previous or\nFuture Health"]
    plt.figure(figsize=(8, 8))
    plt.pie(vals, labels=labels,autopct='%1.0f%%')
    plt.savefig("figures/dcs_breakdown.png")
    plt.clf()

    """
    chronic reasons pie chart
    """
    op_df = df[df['Chronic prev']==1]
    prev_reasons = op_df['System']

    reasons = op_df['System']
    reasons_c = Counter(reasons)
    reas, counts = zip(*sorted(reasons_c.items(), key=lambda x: x[1], reverse=True))
    plt.figure(figsize=(8, 8))
    plt.pie(counts, labels=reas,autopct='%1.0f%%')
    plt.savefig("figures/chronic_reasons.png")
    plt.clf()

    return op_df[[0,2]]


def check_if_uptodate_on_visits(pts, visits, df):
    """ Currently looks like
                       patient_name    dcs_date
    0         Doe John 19181111.xml  26/07/2024
    1         Doe John 19181111.xml  21/08/2024

    returns with 3 extra columns, # visits in year prior to dcs, 3 months prior, and since admission
    """
    df['dcs_date'] = pd.to_datetime(df['dcs_date'], dayfirst=True)

    one = []
    three = []
    after = []

    # take name, find location in pts, get list of visit dates
    for pt_name, dcs_date in df.values:

        # visit is a [date_obj,id] tuple for each visit
        pt_loc = pts.index(pt_name)
        visit_list = visits[pt_loc]

        one_year = dcs_date - timedelta(days=365)
        three_month = dcs_date - timedelta(days=90)

        # i[0] represents the visit date, we want it to be greater than the date one year ago
        # and not greater the discharge date (in the future)
        year_prev = np.sum([one_year <= i[0] <= dcs_date for i in visit_list])
        qtr_prev = np.sum([three_month <= i[0] <= dcs_date for i in visit_list])
        after_dcs = np.sum([i[0]>= dcs_date for i in visit_list])

        one.append(year_prev)
        three.append(qtr_prev)
        after.append(after_dcs)

    df['Visits 365 days before dcs'] = one
    df['Visits 90 days before dcs'] = three
    df['Visits after dcs'] = after


    # add in 2 columns, # visits in year prior to dcs, 3 months prior, and since admission
    return df

def get_demographics(xml):
    """
    Takes a patient xml
    returns demographics in the following order
    [age,gender,aboriginal status,smoking_status]
    """
    try:
        tree = ET.parse(xml)
        root = tree.getroot()
    except:
        print("Error reading XML {}, check for corruption".format(xml))
        return ['invalid']

    # girls == 1 and boys == 2
    sex = root.find('Demographics/Patient/SEXCODE').text
    DOB = root.find('Demographics/Patient/DOB').text
    bday = datetime.strptime(DOB, "%d/%m/%Y %I:%M:%S %p")
    age = datetime.now().year - bday.year - ((datetime.now().month, datetime.now().day) < (bday.month, bday.day))

    #convert to age
    #atsi ? ETHNICCODE ETHNIC1CODE ETHNIC2CODE
    ab = root.find('Demographics/Patient/ETHNICCODE').text
    darts = root.find("ClinicalDetails/ClinicalDetails/SMOKINGSTATUS").text

    return [age,sex,ab,darts]

def main():


    pts = find_all()
    pts = [i for i in pts if i != '.DS_Store']

    conds = [get_conditions("data/pts/{}".format(i)) for i in pts]
    diags = [get_diagnosis("data/pts/{}".format(i)) for i in pts]


    assert len(pts) == len(conds) and len(pts) == len(diags)

    #make df, new diags get rows, conds get columns
    dc_lists = []
    for i, diag in enumerate(diags):
        pt = pts[i]
        cond = conds[i]

        for j in range(len(diag[0])):
            print(diag)
            print(diag[1][j])
            date = diag[1][j].strftime("%d/%m/%Y")
            dc_lists.append([pt]+[diag[0][j]]+[date]+cond)

    dc_df = pd.DataFrame(dc_lists)
    dc_df.to_excel('excel_test.xlsx')


    chronic_patients_df = gather_info()
    chronic_patients_df = chronic_patients_df.rename(columns={0:'patient_name',2:"dcs_date"})
    """ Currently looks like
                       patient_name    dcs_date
    0         Doe John 19181111.xml  26/07/2024
    1         Doe John 19181111.xml  21/08/2024
    """

    visits = [get_visits("data/pts/{}".format(i)) for i in pts]

    # add in 2 columns, # visits in year prior to dcs, 3 months prior, and since admission
    visits_df = check_if_uptodate_on_visits(pts, visits, chronic_patients_df)

    pt_no_visit = visits_df[visits_df['Visits after dcs']==0]['patient_name'].unique()

    demos = [get_demographics("data/pts/{}".format(i)) for i in pt_no_visit]

    for i,j in zip(pt_no_visit,demos):
        print(i,j)


if __name__ == "__main__":
    main()
