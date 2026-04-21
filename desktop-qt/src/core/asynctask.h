#pragma once

#include <QFutureWatcher>
#include <QtConcurrent>
#include <functional>

// runAsync — spustí `task` v Qt thread pool, výsledek předá `onDone` v UI threadu.
//
// Použití ve ViewModelu (QObject):
//   runAsync<std::pair<T,QString>>(this,
//       []() { ApiService api; QString e; return std::pair{api.fetchX(&e), e}; },
//       [this](auto r) { if (!r.second.isEmpty()) emit errorOccurred(r.second);
//                        else emit dataLoaded(r.first); });
//
// Threading:
//   - task lambda běží v QtConcurrent worker threadu
//   - ApiService vytvořený uvnitř lambdy vlastní svůj QNAM v tom threadu — thread-safe
//   - onDone je vždy zavolán v threadu kontextu (UI thread)

template<typename T>
void runAsync(QObject *context,
              std::function<T()> task,
              std::function<void(T)> onDone)
{
    auto *watcher = new QFutureWatcher<T>(context);
    QObject::connect(watcher, &QFutureWatcher<T>::finished,
                     context, [watcher, cb = std::move(onDone)]() mutable {
                         cb(watcher->result());
                         watcher->deleteLater();
                     });
    watcher->setFuture(QtConcurrent::run(std::move(task)));
}
