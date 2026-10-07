// SPDX-License-Identifier: MIT
// Adapter systemu plików FRAM (framfs.h) do abstrakcji microStore::FileSystem, przez którą
// microReticulum zapisuje tablicę tras, znane tożsamości i buforowane ogłoszenia (RNS_USE_FS).
// Tryby otwarcia jak fopen: Read (plik musi istnieć), Write i ReadWrite (tworzy albo obcina),
// Append i ReadAppend (tworzy, zapis zawsze na końcu). Wiele uchwytów jednego pliku widzi
// wspólną długość z węzła. Tylko dla kodu, który i tak dołącza microStore (rns_node.cpp, host).
#pragma once

#include <microStore/File.h>
#include <microStore/FileSystem.h>

#include <string.h>

#include "framfs.h"

namespace rnsfs {

class FramFile : public microStore::FileImpl {
public:
    FramFile(framfs::Fs& fs, int inode, bool append) : fs_(fs), inode_(inode), append_(append) {
        fs_.name(inode_, name_);
    }

protected:
    const char* name() const override { return name_; }
    size_t size() const override { return fs_.size(inode_); }
    void close() override { open_ = false; }
    int read() override {
        uint8_t c;
        return read(&c, 1) == 1 ? c : -1;
    }
    size_t write(uint8_t ch) override { return write(&ch, 1); }
    size_t read(uint8_t* buffer, size_t count) override {
        if (!open_) return 0;
        const size_t n = fs_.read(inode_, position_, buffer, count);
        position_ += n;
        return n;
    }
    size_t write(const uint8_t* buffer, size_t count) override {
        if (!open_) return 0;
        if (append_) position_ = fs_.size(inode_);
        const size_t n = fs_.write(inode_, position_, buffer, count);
        position_ += n;
        return n;
    }
    int available() override {
        const size_t s = fs_.size(inode_);
        return open_ && position_ < s ? (int)(s - position_) : 0;
    }
    int peek() override {
        uint8_t c;
        return open_ && fs_.read(inode_, position_, &c, 1) == 1 ? c : -1;
    }
    size_t tell() override { return position_; }
    long seek(uint32_t pos, microStore::SeekMode mode) override {
        const size_t s = fs_.size(inode_);
        size_t target = pos;
        if (mode == microStore::SeekModeCur) target = position_ + pos;
        else if (mode == microStore::SeekModeEnd) target = s + pos;
        if (target > s) return -1;
        position_ = target;
        return 0;
    }
    void flush() override {}
    bool isValid() const override { return open_ && inode_ >= 0; }

private:
    framfs::Fs& fs_;
    int inode_;
    bool append_;
    bool open_ = true;
    uint32_t position_ = 0;
    char name_[framfs::NAME_LEN + 1] = {};
};

class FramFileSystem : public microStore::FileSystemImpl {
public:
    explicit FramFileSystem(framfs::Fs& fs) : fs_(fs) {}

protected:
    bool format() override { return fs_.format(); }
    bool init(bool) override { return fs_.mounted() || fs_.mount(); }
    microStore::File open(const char* path, microStore::File::Mode mode, const bool) override {
        int inode = -1;
        bool append = false;
        switch (mode) {
            case microStore::File::ModeRead: inode = fs_.find(path); break;
            case microStore::File::ModeWrite:
            case microStore::File::ModeReadWrite: inode = fs_.create(path); break;
            case microStore::File::ModeAppend:
            case microStore::File::ModeReadAppend:
                inode = fs_.find(path);
                if (inode < 0) inode = fs_.create(path);
                append = true;
                break;
        }
        if (inode < 0) return {};
        return microStore::File(new FramFile(fs_, inode, append));
    }
    bool exists(const char* path) override { return fs_.find(path) >= 0; }
    bool remove(const char* path) override { return fs_.remove(path); }
    bool rename(const char* from, const char* to) override { return fs_.rename(from, to); }
    bool mkdir(const char*) override { return true; }   // katalogi są przedrostkami nazw
    bool rmdir(const char* path) override { return fs_.removeDirectory(path); }
    bool isDirectory(const char* path) override { return fs_.directoryExists(path); }
    std::list<std::string> listDirectory(const char* path, Callbacks::DirectoryListing callback = nullptr) override {
        struct Context {
            std::list<std::string>* files;
            Callbacks::DirectoryListing* callback;
        };
        std::list<std::string> files;
        Context context{&files, &callback};
        fs_.list(path, [](const char* name, void* raw) {
            Context* c = static_cast<Context*>(raw);
            if (*c->callback) (*c->callback)(name);
            else c->files->push_back(name);
        }, &context);
        return files;
    }
    size_t storageSize() override { return fs_.capacityBytes(); }
    size_t storageAvailable() override { return fs_.freeBytes(); }

private:
    framfs::Fs& fs_;
};

}  // namespace rnsfs
