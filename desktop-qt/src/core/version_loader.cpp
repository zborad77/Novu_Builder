#include "core/version_loader.hpp"

#include <QCoreApplication>
#include <QDebug>
#include <QDir>
#include <QFile>
#include <QIODevice>

namespace novu::core {

static QString parseManifestVersion(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
        return {};

    while (!file.atEnd()) {
        const QString line = QString::fromUtf8(file.readLine()).trimmed();
        if (line.startsWith(QStringLiteral("version="))) {
            const QString version = line.mid(8).trimmed();
            if (!version.isEmpty())
                return version;
        }
    }
    return {};
}

QString loadAppVersion()
{
    const QString appDir = QCoreApplication::applicationDirPath();

    // 1. install.manifest next to executable (standalone / build)
    const QString localPath = appDir + QStringLiteral("/install.manifest");
    QString version = parseManifestVersion(localPath);
    if (!version.isEmpty()) {
        qDebug() << "[VERSION LOADED]" << version << "from" << localPath;
        return version;
    }

    // 2. install.manifest one level up (installed: applications/{slug}/install.manifest)
    const QString parentPath = QDir::cleanPath(appDir + QStringLiteral("/../install.manifest"));
    version = parseManifestVersion(parentPath);
    if (!version.isEmpty()) {
        qDebug() << "[VERSION LOADED]" << version << "from" << parentPath;
        return version;
    }

    qWarning() << "[VERSION] install.manifest not found at" << localPath << "or" << parentPath;
    return QStringLiteral("unknown");
}

} // namespace novu::core
