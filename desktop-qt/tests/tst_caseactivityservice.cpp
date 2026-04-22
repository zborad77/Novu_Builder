#include <QSignalSpy>
#include <QTest>
#include <QTimer>

#include "services/caseactivityservice.h"
#include "services/icaseactivitystreamclient.h"

// ---------------------------------------------------------------------------
// FakeStreamClient
// ---------------------------------------------------------------------------

class FakeStreamClient : public ICaseActivityStreamClient
{
    Q_OBJECT
public:
    FakeStreamClient() : ICaseActivityStreamClient(nullptr) {}

    void subscribeToCase(const QString &caseId, const QString &jobId = {}) override
    {
        lastCaseId = caseId;
        lastJobId = jobId;
        ++subscribeCount;
    }

    void clearSubscription() override
    {
        lastCaseId.clear();
        lastJobId.clear();
    }

    bool isConnected() const override { return m_connected; }

    void setConnected(bool c)
    {
        m_connected = c;
        emit connectionStateChanged(c);
    }

    void emitJobStatus(const QString &caseId, const QString &jobId, const QString &status)
    {
        emit jobStatusChanged(caseId, jobId, status);
    }

    QString lastCaseId;
    QString lastJobId;
    int subscribeCount = 0;
    bool m_connected = false;
};

// ---------------------------------------------------------------------------
// TestableService
// ---------------------------------------------------------------------------

struct PendingAnalysisPoll {
    QString jobId;
    std::function<void(QString)> onSuccess;
    std::function<void(QString)> onError;
};

class TestableService : public CaseActivityService
{
    Q_OBJECT
public:
    explicit TestableService(FakeStreamClient *stream, QObject *parent = nullptr)
        : CaseActivityService(stream, parent)
    {}

    QList<PendingAnalysisPoll> pendingAnalysis;

protected:
    void apiGetAnalysisJobStatus(const QString &jobId,
                                 std::function<void(QString)> onSuccess,
                                 std::function<void(QString)> onError) override
    {
        pendingAnalysis.append({jobId, std::move(onSuccess), std::move(onError)});
    }

    void apiFetchCaseImages(const QString &,
                             std::function<void(std::vector<ImageDto>)> onSuccess,
                             std::function<void(QString)>) override
    {
        onSuccess({});
    }
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

class TestCaseActivityService : public QObject
{
    Q_OBJECT

private slots:

    // ---- Snapshot flag mechanics ----------------------------------------

    // Connecting the stream alone must not set the snapshot flag.
    // If the flag were set by the connect event, the catch-up poll that fires
    // on justBecameAvailable would be suppressed — we'd see no poll.
    void connectAloneDoesNotSetSnapshotFlag()
    {
        FakeStreamClient stream;
        TestableService svc(&stream);

        svc.startAnalysisStatusMonitoring("case1", "job1");
        QCOMPARE(svc.pendingAnalysis.size(), 1);  // fallback poll

        stream.setConnected(true);
        // If connect had erroneously set hasSnapshot=true, this would still be 1.
        QCOMPARE(svc.pendingAnalysis.size(), 2);  // + catch-up
    }

    // The flag must remain false across multiple connect/disconnect cycles
    // as long as no actual status data is received between them.
    // Each reconnect must produce a fresh catch-up poll.
    void multipleReconnectsWithoutDataKeepFlagFalse()
    {
        FakeStreamClient stream;
        TestableService svc(&stream);
        svc.startAnalysisStatusMonitoring("case1", "job1");

        // Cycle 1
        stream.setConnected(true);
        int pollsAfterConnect1 = svc.pendingAnalysis.size();

        stream.setConnected(false);
        stream.setConnected(true);
        int pollsAfterConnect2 = svc.pendingAnalysis.size();

        stream.setConnected(false);
        stream.setConnected(true);
        int pollsAfterConnect3 = svc.pendingAnalysis.size();

        // Each reconnect without data must add exactly one catch-up poll.
        QVERIFY(pollsAfterConnect2 > pollsAfterConnect1);
        QVERIFY(pollsAfterConnect3 > pollsAfterConnect2);
    }

    // A realtime jobStatusChanged event sets m_lastAnalysisJobStatus, evidenced
    // by deduplication: the same status is not re-emitted.
    void realtimeEventSetsSnapshotFlag()
    {
        FakeStreamClient stream;
        TestableService svc(&stream);
        stream.setConnected(true);
        svc.startAnalysisStatusMonitoring("case1", "job1");

        QSignalSpy spy(&svc, &CaseActivityService::analysisStatusReceived);

        stream.emitJobStatus("case1", "job1", "running");
        QCOMPARE(spy.count(), 1);
        QCOMPARE(spy.at(0).at(2).toString(), QString("running"));

        // Same status again → deduplicated
        stream.emitJobStatus("case1", "job1", "running");
        QCOMPARE(spy.count(), 1);

        // Status change propagates
        stream.emitJobStatus("case1", "job1", "completed");
        QCOMPARE(spy.count(), 2);
    }

    // ---- Terminal status guard -----------------------------------------

    // After a terminal status (completed/failed/error/cancelled) is emitted,
    // every subsequent event — regardless of source, status value, or order —
    // must be silently discarded. This is the most critical guard in the system:
    // a job that has finished must never appear to un-finish.
    void terminalStatusBlocksAllSubsequentEvents()
    {
        FakeStreamClient stream;
        TestableService svc(&stream);
        stream.setConnected(true);
        svc.startAnalysisStatusMonitoring("case1", "job1");

        QSignalSpy spy(&svc, &CaseActivityService::analysisStatusReceived);

        stream.emitJobStatus("case1", "job1", "running");
        QCOMPARE(spy.count(), 1);

        stream.emitJobStatus("case1", "job1", "completed");
        QCOMPARE(spy.count(), 2);

        // Out-of-order realtime "running" after completed → discarded
        stream.emitJobStatus("case1", "job1", "running");
        QCOMPARE(spy.count(), 2);

        // Another terminal status after completed → discarded
        stream.emitJobStatus("case1", "job1", "failed");
        QCOMPARE(spy.count(), 2);

        // Duplicate completed → discarded
        stream.emitJobStatus("case1", "job1", "completed");
        QCOMPARE(spy.count(), 2);

        // Late poll response after terminal → discarded
        QVERIFY(!svc.pendingAnalysis.isEmpty());
        svc.pendingAnalysis.first().onSuccess("running");
        QCOMPARE(spy.count(), 2);
    }

    // ---- In-flight callback guards -------------------------------------

    // An in-flight poll callback that arrives after stopAnalysisStatusMonitoring
    // must be discarded (monitored IDs are cleared → caseId guard fires).
    void pollResponseAfterStopIsDiscarded()
    {
        FakeStreamClient stream;
        TestableService svc(&stream);

        svc.startAnalysisStatusMonitoring("case1", "job1");
        QCOMPARE(svc.pendingAnalysis.size(), 1);

        PendingAnalysisPoll staleCallback = svc.pendingAnalysis.takeFirst();
        svc.stopAnalysisStatusMonitoring();

        QSignalSpy spy(&svc, &CaseActivityService::analysisStatusReceived);
        staleCallback.onSuccess("running");
        QCOMPARE(spy.count(), 0);
    }

    // A poll response for a previous job must be discarded when a new job
    // is already being monitored (jobId guard fires).
    void pollResponseOfOldJobIsDiscarded()
    {
        FakeStreamClient stream;
        TestableService svc(&stream);

        svc.startAnalysisStatusMonitoring("case1", "job1");
        PendingAnalysisPoll oldCallback = svc.pendingAnalysis.takeFirst();

        svc.startAnalysisStatusMonitoring("case1", "job2");

        QSignalSpy spy(&svc, &CaseActivityService::analysisStatusReceived);

        // Old job1 callback → discarded
        oldCallback.onSuccess("running");
        QCOMPARE(spy.count(), 0);

        // New job2 callback → propagated
        QVERIFY(!svc.pendingAnalysis.isEmpty());
        svc.pendingAnalysis.first().onSuccess("running");
        QCOMPARE(spy.count(), 1);
        QCOMPARE(spy.at(0).at(1).toString(), QString("job2"));
    }

    // ---- Reconnect / catch-up logic ------------------------------------

    // When the stream reconnects and no snapshot has been received yet,
    // a catch-up poll is triggered each time.
    void reconnectWithoutSnapshotTriggersCatchup()
    {
        FakeStreamClient stream;
        TestableService svc(&stream);

        svc.startAnalysisStatusMonitoring("case1", "job1");
        QCOMPARE(svc.pendingAnalysis.size(), 1);  // fallback poll

        stream.setConnected(true);
        QCOMPARE(svc.pendingAnalysis.size(), 2);  // + catch-up

        stream.setConnected(false);
        int pollsAfterDisconnect = svc.pendingAnalysis.size();

        stream.setConnected(true);
        QCOMPARE(svc.pendingAnalysis.size(), pollsAfterDisconnect + 1);
    }

    // When a poll response has already set the snapshot flag, a subsequent
    // stream connection must NOT trigger a redundant catch-up poll.
    void reconnectWithSnapshotSkipsCatchup()
    {
        FakeStreamClient stream;
        TestableService svc(&stream);

        svc.startAnalysisStatusMonitoring("case1", "job1");
        QCOMPARE(svc.pendingAnalysis.size(), 1);

        // Poll resolves while disconnected → hasSnapshot=true
        svc.pendingAnalysis.first().onSuccess("running");
        svc.pendingAnalysis.clear();

        // Connect → justBecameAvailable=true, hasSnapshot=true → no catch-up
        stream.setConnected(true);
        QCOMPARE(svc.pendingAnalysis.size(), 0);
    }

    // ---- Async / event-loop tests --------------------------------------
    //
    // These two tests verify that the same guards hold when events are
    // delivered via the Qt event loop rather than from within a direct
    // synchronous call stack — the scenario closest to production WS behaviour.

    // Realtime snapshot arrives synchronously; a delayed poll response with
    // the same status must be deduplicated even after an event-loop yield.
    void delayedPollAfterRealtimeSnapshotIsDeduped()
    {
        FakeStreamClient stream;
        TestableService svc(&stream);
        stream.setConnected(true);
        svc.startAnalysisStatusMonitoring("case1", "job1");

        // Capture the pending catch-up poll callback before resolving it later
        QVERIFY(!svc.pendingAnalysis.isEmpty());
        PendingAnalysisPoll pendingPoll = svc.pendingAnalysis.takeFirst();

        QSignalSpy spy(&svc, &CaseActivityService::analysisStatusReceived);

        // Realtime event arrives first (synchronous)
        stream.emitJobStatus("case1", "job1", "running");
        QCOMPARE(spy.count(), 1);

        // Delayed poll response for the same status arrives via event loop
        QTimer::singleShot(0, this, [&pendingPoll]() {
            pendingPoll.onSuccess("running");
        });
        QTest::qWait(50);

        // Deduplicated — m_lastAnalysisJobStatus already "running"
        QCOMPARE(spy.count(), 1);
    }

    // Terminal status arrives synchronously; a delayed out-of-order realtime
    // event must be discarded even after an event-loop yield.
    void outOfOrderRealtimeAfterTerminalIsDiscarded()
    {
        FakeStreamClient stream;
        TestableService svc(&stream);
        stream.setConnected(true);
        svc.startAnalysisStatusMonitoring("case1", "job1");

        QSignalSpy spy(&svc, &CaseActivityService::analysisStatusReceived);

        // Terminal status arrives (synchronous)
        stream.emitJobStatus("case1", "job1", "completed");
        QCOMPARE(spy.count(), 1);

        // Delayed stale "running" arrives via event loop (out-of-order WS packet)
        QTimer::singleShot(0, &stream, [&stream]() {
            stream.emitJobStatus("case1", "job1", "running");
        });
        QTest::qWait(50);

        // Terminal guard discards the late event
        QCOMPARE(spy.count(), 1);
    }
};

QTEST_MAIN(TestCaseActivityService)
#include "tst_caseactivityservice.moc"
