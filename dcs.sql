SELECT *
FROM BPS_Patients
WHERE StatusText = 'Active'
AND InternalID IN (SELECT InternalID
  FROM CorrespondenceIn
  WHERE Subject LIKE '%Discharge%'
  AND CorrespondenceDate >= DATEADD(month, -6, getdate())
  AND RecordStatus = 1)
AND InternalID NOT IN (SELECT InternalID
  FROM VISITS
  WHERE RECORDSTATUS = 1
  AND VISITDATE >= DATEADD(month, -6, getdate())
  AND VISITCODE = 1)
ORDER BY surname, firstname
