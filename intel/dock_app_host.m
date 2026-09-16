#import <Cocoa/Cocoa.h>

@interface YYBDockAppDelegate : NSObject <NSApplicationDelegate>
@property(nonatomic, strong) NSTask *launchTask;
@property(nonatomic, copy) NSArray<NSString *> *launchArguments;
@property(nonatomic) BOOL terminating;
@property(nonatomic) BOOL launchTaskFinished;
@property(nonatomic, strong) id windowShownObserver;
@property(nonatomic, copy) NSString *lastOpenedGamePath;
@property(nonatomic, strong) NSDate *lastOpenedGameAt;
@property(nonatomic) BOOL launchpadSyncInProgress;
@end

@implementation YYBDockAppDelegate

- (NSString *)windowsProcessName {
    NSString *mode = self.launchArguments.firstObject;
    if ([mode isEqualToString:@"steam"]) return @"steam.exe";
    if ([mode isEqualToString:@"netease"]) return @"FeverGamesInstaller.exe";
    if ([mode isEqualToString:@"netease-game"]) return @"Sky.exe";
    if ([mode isEqualToString:@"steam-game"]) {
        NSArray *names = NSBundle.mainBundle.infoDictionary[@"YYBWindowsExecutables"];
        if ([names isKindOfClass:NSArray.class] && names.count > 0) return names.firstObject;
    }
    return nil;
}

- (NSString *)stringInDictionary:(NSDictionary *)dictionary
                             keys:(NSArray<NSString *> *)keys {
    for (NSString *key in keys) {
        id value = dictionary[key];
        if ([value isKindOfClass:NSString.class] && [value length] > 0) return value;
    }
    return nil;
}

- (BOOL)eventPackage:(NSString *)package
           executable:(NSString *)executable
          matchesInfo:(NSDictionary *)info {
    NSString *mode = self.launchArguments.firstObject;
    NSString *expectedPlatform = [mode isEqualToString:@"steam"] ? @"steam" : @"netease";
    NSString *platform = info[@"YYBPlatform"];
    if (![platform isKindOfClass:NSString.class] ||
        [platform caseInsensitiveCompare:expectedPlatform] != NSOrderedSame) return NO;

    NSString *expectedPackage = info[@"YYBPackageName"];
    if (package.length > 0 && [expectedPackage isKindOfClass:NSString.class] &&
        [package caseInsensitiveCompare:expectedPackage] == NSOrderedSame) return YES;

    NSString *eventName = executable.lastPathComponent;
    if (eventName.length == 0) return NO;
    NSArray *executables = info[@"YYBWindowsExecutables"];
    if (![executables isKindOfClass:NSArray.class]) return NO;
    for (id candidate in executables) {
        if ([candidate isKindOfClass:NSString.class] &&
            [eventName caseInsensitiveCompare:[candidate lastPathComponent]] == NSOrderedSame) {
            return YES;
        }
    }
    return NO;
}

- (void)openGeneratedAppForPackage:(NSString *)package
                         executable:(NSString *)executable
                          allowSync:(BOOL)allowSync {
    NSMutableArray<NSString *> *roots = [NSMutableArray arrayWithObject:@"/Applications"];
    NSString *userApplications = [NSHomeDirectory() stringByAppendingPathComponent:@"Applications"];
    if (![userApplications isEqualToString:@"/Applications"]) [roots addObject:userApplications];
    NSString *currentPath = NSBundle.mainBundle.bundlePath.stringByStandardizingPath;
    NSFileManager *files = NSFileManager.defaultManager;

    for (NSString *root in roots) {
        NSArray<NSString *> *entries = [files contentsOfDirectoryAtPath:root error:nil];
        for (NSString *entry in entries) {
            if ([entry.pathExtension caseInsensitiveCompare:@"app"] != NSOrderedSame) continue;
            NSString *appPath = [[root stringByAppendingPathComponent:entry] stringByStandardizingPath];
            if ([appPath isEqualToString:currentPath]) continue;
            NSString *plist = [appPath stringByAppendingPathComponent:@"Contents/Info.plist"];
            NSDictionary *info = [NSDictionary dictionaryWithContentsOfFile:plist];
            if (![info[@"YYBIntelLaunchpadManaged"] boolValue]) continue;
            if (![self eventPackage:package executable:executable matchesInfo:info]) continue;

            if ([self.lastOpenedGamePath isEqualToString:appPath] && self.lastOpenedGameAt &&
                [NSDate.date timeIntervalSinceDate:self.lastOpenedGameAt] < 2.0) return;
            self.lastOpenedGamePath = appPath;
            self.lastOpenedGameAt = NSDate.date;

            NSWorkspaceOpenConfiguration *configuration =
                [NSWorkspaceOpenConfiguration configuration];
            configuration.activates = NO;
            [NSWorkspace.sharedWorkspace
                openApplicationAtURL:[NSURL fileURLWithPath:appPath]
                configuration:configuration
                completionHandler:^(NSRunningApplication *application, NSError *error) {
                    (void)application;
                    (void)error;
                }];
            return;
        }
    }

    if (!allowSync || self.launchpadSyncInProgress) return;
    NSString *syncPath = [NSHomeDirectory() stringByAppendingPathComponent:
        @"Library/Application Support/YYBIntelLauncher/bin/sync-launchpad-apps.py"];
    if (![files isExecutableFileAtPath:syncPath]) return;
    self.launchpadSyncInProgress = YES;
    NSTask *syncTask = [[NSTask alloc] init];
    syncTask.executableURL = [NSURL fileURLWithPath:syncPath];
    __weak YYBDockAppDelegate *weakSelf = self;
    syncTask.terminationHandler = ^(NSTask *task) {
        (void)task;
        dispatch_async(dispatch_get_main_queue(), ^{
            YYBDockAppDelegate *delegate = weakSelf;
            if (!delegate) return;
            delegate.launchpadSyncInProgress = NO;
            [delegate openGeneratedAppForPackage:package
                                       executable:executable
                                        allowSync:NO];
        });
    };
    NSError *error = nil;
    if (![syncTask launchAndReturnError:&error]) self.launchpadSyncInProgress = NO;
}

- (void)startEngineEventBridge {
    NSString *mode = self.launchArguments.firstObject;
    if (![mode isEqualToString:@"steam"] && ![mode isEqualToString:@"netease"]) return;
    __weak YYBDockAppDelegate *weakSelf = self;
    self.windowShownObserver = [NSDistributedNotificationCenter.defaultCenter
        addObserverForName:@"com.tencent.yyb.wine.appWindowShown"
                    object:nil
                     queue:NSOperationQueue.mainQueue
        usingBlock:^(NSNotification *notification) {
            YYBDockAppDelegate *delegate = weakSelf;
            if (!delegate || delegate.terminating) return;
            NSDictionary *info = [notification.userInfo isKindOfClass:NSDictionary.class]
                ? notification.userInfo : @{};
            NSString *package = [delegate stringInDictionary:info
                keys:@[@"pkgName", @"packageName", @"package_name", @"package"]];
            NSString *executable = [delegate stringInDictionary:info
                keys:@[@"exeName", @"executable", @"exe_name"]];
            [delegate openGeneratedAppForPackage:package
                                       executable:executable
                                        allowSync:YES];
        }];
}

- (void)activateWindowsProcess {
    NSString *expected = self.windowsProcessName;
    if (!expected) return;
    for (NSRunningApplication *application in
         NSWorkspace.sharedWorkspace.runningApplications) {
        if ([application.localizedName caseInsensitiveCompare:expected] ==
            NSOrderedSame) {
            [application activateWithOptions:NSApplicationActivateAllWindows];
        }
    }
}

- (NSString *)launcherPath {
    return [NSHomeDirectory()
        stringByAppendingPathComponent:
            @"Library/Application Support/YYBIntelLauncher/bin/launch-windows-app"];
}

- (BOOL)isWindowsModeRunning:(NSString *)mode {
    NSString *helper = [NSHomeDirectory()
        stringByAppendingPathComponent:
            @"Library/Application Support/YYBIntelLauncher/bin/windows-app-process.py"];
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:helper]) return NO;
    NSTask *checkTask = [[NSTask alloc] init];
    checkTask.executableURL = [NSURL fileURLWithPath:helper];
    checkTask.arguments = @[@"--check", mode];
    NSError *error = nil;
    if (![checkTask launchAndReturnError:&error]) return NO;
    [checkTask waitUntilExit];
    return checkTask.terminationStatus == 0;
}

- (BOOL)hasRunningGeneratedGameForPlatform:(NSString *)platform {
    NSString *prefix = [NSString stringWithFormat:@"local.yybintel.game.%@.", platform];
    for (NSRunningApplication *application in
         NSWorkspace.sharedWorkspace.runningApplications) {
        if ([application.bundleIdentifier hasPrefix:prefix]) return YES;
    }
    return NO;
}

- (void)showLaunchError:(NSString *)message {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.alertStyle = NSAlertStyleCritical;
    alert.messageText = @"无法启动";
    alert.informativeText = message;
    [alert runModal];
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    id configured = NSBundle.mainBundle.infoDictionary[@"YYBLaunchArguments"];
    if (![configured isKindOfClass:NSArray.class] || [configured count] == 0) {
        [self showLaunchError:@"这个 App 缺少 Windows 启动参数，请重新运行安装程序。"];
        [NSApp terminate:nil];
        return;
    }
    self.launchArguments = configured;
    [self startEngineEventBridge];

    NSString *launcher = self.launcherPath;
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:launcher]) {
        [self showLaunchError:@"启动组件不完整，请重新运行安装程序。"];
        [NSApp terminate:nil];
        return;
    }

    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:launcher];
    task.arguments = self.launchArguments;
    NSMutableDictionary *environment = NSProcessInfo.processInfo.environment.mutableCopy;
    environment[@"YYB_DOCK_HOST"] = @"1";
    task.environment = environment;
    __weak YYBDockAppDelegate *weakSelf = self;
    task.terminationHandler = ^(NSTask *finishedTask) {
        (void)finishedTask;
        dispatch_async(dispatch_get_main_queue(), ^{
            YYBDockAppDelegate *delegate = weakSelf;
            if (delegate && !delegate.terminating) {
                delegate.launchTaskFinished = YES;
                [NSApp terminate:nil];
            }
        });
    };
    NSError *error = nil;
    if (![task launchAndReturnError:&error]) {
        [self showLaunchError:error.localizedDescription ?: @"未知启动错误"];
        [NSApp terminate:nil];
        return;
    }
    self.launchTask = task;
    [NSApp activateIgnoringOtherApps:YES];
}

- (void)dealloc {
    if (self.windowShownObserver) {
        [NSDistributedNotificationCenter.defaultCenter
            removeObserver:self.windowShownObserver];
    }
}

- (BOOL)applicationShouldHandleReopen:(NSApplication *)sender
                    hasVisibleWindows:(BOOL)flag {
    (void)sender;
    (void)flag;
    [self activateWindowsProcess];
    return YES;
}

- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    (void)sender;
    NSString *mode = self.launchArguments.firstObject;
    if (!self.launchTaskFinished && [mode isEqualToString:@"netease"] &&
        [self isWindowsModeRunning:@"netease-game"]) {
        // Sky asks FeverGames for its login ticket after its window appears.
        // Keep both the bridge and Dock item alive until the game exits, so the
        // launcher never becomes an unmanageable background-only process.
        NSAlert *alert = [[NSAlert alloc] init];
        alert.alertStyle = NSAlertStyleInformational;
        alert.messageText = @"光·遇仍在运行";
        alert.informativeText =
            @"网易登录服务需要保持运行。请先从“光·遇”Dock 图标退出游戏，再退出网易游戏启动器。";
        [alert runModal];
        return NSTerminateCancel;
    }
    if (!self.launchTaskFinished && [mode isEqualToString:@"steam"] &&
        [self hasRunningGeneratedGameForPlatform:@"steam"]) {
        NSAlert *alert = [[NSAlert alloc] init];
        alert.alertStyle = NSAlertStyleInformational;
        alert.messageText = @"Steam 游戏仍在运行";
        alert.informativeText =
            @"请先从对应游戏的 Dock 图标退出游戏，再退出 Windows 版 Steam。";
        [alert runModal];
        return NSTerminateCancel;
    }
    self.terminating = YES;
    // Stop the event-pump bridge first so it cannot recreate helper
    // processes while the app-specific cleanup is running.
    if (self.launchTask.running) {
        [self.launchTask terminate];
        [self.launchTask waitUntilExit];
    }
    if (self.launchArguments.count > 0) {
        NSTask *stopTask = [[NSTask alloc] init];
        stopTask.executableURL = [NSURL fileURLWithPath:self.launcherPath];
        stopTask.arguments = [@[@"--stop"]
            arrayByAddingObjectsFromArray:self.launchArguments];
        NSError *error = nil;
        if ([stopTask launchAndReturnError:&error]) [stopTask waitUntilExit];
    }
    return NSTerminateNow;
}

@end

static void InstallApplicationMenu(void) {
    NSString *name = NSProcessInfo.processInfo.processName;
    NSMenu *menuBar = [[NSMenu alloc] init];
    NSMenuItem *applicationItem = [[NSMenuItem alloc] init];
    [menuBar addItem:applicationItem];
    NSApp.mainMenu = menuBar;

    NSMenu *applicationMenu = [[NSMenu alloc] init];
    NSString *quitTitle = [@"退出 " stringByAppendingString:name];
    NSMenuItem *quit = [[NSMenuItem alloc]
        initWithTitle:quitTitle
               action:@selector(terminate:)
        keyEquivalent:@"q"];
    [applicationMenu addItem:quit];
    applicationItem.submenu = applicationMenu;
}

int main(int argc, const char *argv[]) {
    (void)argc;
    (void)argv;
    @autoreleasepool {
        NSApplication *application = NSApplication.sharedApplication;
        [application setActivationPolicy:NSApplicationActivationPolicyRegular];
        InstallApplicationMenu();
        YYBDockAppDelegate *delegate = [[YYBDockAppDelegate alloc] init];
        application.delegate = delegate;
        [application run];
    }
    return 0;
}
