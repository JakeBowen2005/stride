from app.api.wellness import recovery_signals, training_status_label
from app.services.wellness import parse_day

SUMMARY = {"restingHeartRate": 41, "lastSevenDaysAvgRestingHeartRate": 43, "bodyBatteryMostRecentValue": 58,
           "bodyBatteryAtWakeTime": 95, "averageStressLevel": 20, "totalSteps": 11996, "dailyStepGoal": 19840}
SLEEP = {"dailySleepDTO": {"sleepTimeSeconds": 25980, "deepSleepSeconds": 5700, "remSleepSeconds": 5340,
                           "sleepScores": {"overall": {"value": 89, "qualifierKey": "GOOD"}}}}
HRV = {"hrvSummary": {"lastNightAvg": 103, "weeklyAvg": 97, "status": "BALANCED",
                      "baseline": {"balancedLow": 78, "balancedUpper": 115}}}
READINESS = [{"score": 70, "level": "MODERATE", "feedbackShort": "RECOVERY_IN_PROGRESS", "recoveryTime": 1385}]
STATUS = {"mostRecentTrainingStatus": {"latestTrainingStatusData": {"123": {
              "trainingStatusFeedbackPhrase": "PRODUCTIVE_3",
              "acuteTrainingLoadDTO": {"dailyTrainingLoadAcute": 585, "dailyTrainingLoadChronic": 466,
                                       "dailyAcuteChronicWorkloadRatio": 1.2}}}},
          "mostRecentVO2Max": {"generic": {"vo2MaxPreciseValue": 53.3}}}
PRED = {"time5K": 1280, "time10K": 2784, "timeHalfMarathon": 6387, "timeMarathon": 14310}


def test_parse_day_real_shapes():
    d = parse_day(SUMMARY, SLEEP, HRV, READINESS, STATUS, PRED)
    assert d["resting_hr"] == 41 and d["sleep_score"] == 89 and d["hrv_last_night"] == 103
    assert d["readiness_score"] == 70 and d["training_status"] == "PRODUCTIVE_3"
    assert d["acwr"] == 1.2 and d["vo2max"] == 53.3 and d["predicted_5k"] == 1280
    assert d["body_battery_wake"] == 95 and d["steps"] == 11996


def test_parse_day_tolerates_missing_endpoints():
    assert parse_day(None, None, None, None, None, None) == {}
    assert parse_day({"averageStressLevel": -1}, {}, {}, [], {}, None).get("stress_avg") is None


def test_recovery_signals():
    good = {"hrv_last_night": 103, "hrv_baseline_low": 78, "resting_hr": 41, "resting_hr_7d_avg": 43,
            "sleep_seconds": 26000, "readiness_score": 80}
    assert [s["level"] for s in recovery_signals(good)] == ["good"]
    tired = {"hrv_last_night": 60, "hrv_baseline_low": 78, "resting_hr": 50, "resting_hr_7d_avg": 43,
             "sleep_seconds": 5 * 3600, "acwr": 1.6}
    assert {s["metric"] for s in recovery_signals(tired)} == {"hrv", "resting_hr", "sleep", "acwr"}


def test_training_status_label():
    assert training_status_label("PRODUCTIVE_3") == "Productive"
    assert training_status_label(None) is None
