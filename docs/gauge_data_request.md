# Observed discharge: what we use now and how to request gauge data

## Observed vs modelled discharge

| | CWC gauge (Beas at Bhuntar) | GloFAS v4 reanalysis (used now) |
|---|---|---|
| what it is | measured river flow at a gauging station | output of a hydrological model (LISFLOOD) driven by ERA5 weather |
| access | restricted (Indus-basin data are classified on India-WRIS) | open, CC BY 4.0, via Open-Meteo Flood API |
| location | the gauge itself | 0.05 deg grid cell at 31.825 N, 77.125 E, chosen on the Beas main stem below the Parvati confluence |
| known issues | gaps, rating-curve changes | snowmelt timing bias (little rise in Apr-Jun at this cell); no reservoir or diversion operations; errors in ERA5 propagate |

Consequences for this project: forecast skill, interval coverage and drift results measure how well
the models reproduce GloFAS, not the real river. Reports state `target_is_observed: false`. Nothing
in the repository claims access to gauge observations.

## Switching to gauge data

Place a CSV at `data/raw/discharge_gauge.csv` with columns `date` (YYYY-MM-DD) and
`discharge_m3s` (daily mean, m3/s). `python -m src.ingest.discharge` then uses it instead of
GloFAS, the provenance manifest records it, and every report switches to
`target_is_observed: true`. Re-run features, training (new registered protocol and test), drift
replay and the dashboard. Do not mix gauge and GloFAS values in one series.

## Checklist before sending a request

- [ ] Supervisor agrees and signs; department letterhead.
- [ ] Station: Beas at Bhuntar (CWC), with the station code if your supervisor has it.
- [ ] Variables: daily mean discharge (m3/s); daily gauge height optional.
- [ ] Period: 2015-01-01 to the latest available date.
- [ ] Format: CSV or Excel, one row per day, missing days marked.
- [ ] Purpose: non-commercial academic research (semester project), no redistribution of raw data.
- [ ] Where to send: CWC regional office responsible for the Beas (Indus basin), or through
      India-WRIS's data-request process; your supervisor may know the correct office.
- [ ] Expect weeks to months; Indus-basin data may be refused. GloFAS stays the documented fallback.

## Draft letter (edit before sending)

> To: The Executive Engineer / Superintending Engineer, Central Water Commission, [regional office]
>
> Subject: Request for daily discharge data, Beas at Bhuntar, for academic research
>
> Sir/Madam,
>
> I am [name], a [programme, semester] student at [institution], working under the supervision
> of [supervisor name, designation] on a research project on probabilistic short- and medium-range
> discharge forecasting for the Beas above Bhuntar using satellite snow cover and meteorological
> reanalysis.
>
> We request daily mean discharge (m3/s) for the Bhuntar gauging station for 1 January 2015 to
> the latest available date, preferably as CSV or Excel. The data will be used only for
> non-commercial academic research, will not be redistributed, and will be acknowledged to CWC in
> any report or publication. We will comply with any conditions on use or confidentiality.
>
> The project currently uses modelled GloFAS discharge; observed data would allow us to validate
> the forecasts against the real river.
>
> A letter from my supervisor is attached. Thank you for considering this request.
>
> Yours faithfully,
> [name, roll number, contact]
> Endorsed by: [supervisor name, signature, department]
