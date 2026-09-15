#import <Cocoa/Cocoa.h>

@interface YYBDockAppDelegate : NSObject <NSApplicationDelegate>
@property(nonatomic, strong) NSTask *launchTask;
@property(nonatomic, copy) NSArray<NSString *> *launchArguments;
@property(nonatomic) BOOL terminating;
@end

@implementation YYBDockAppDelegate

- (NSString *)windowsProcessName {
    NSString *mode = self.launchArguments.firstObject;
    if ([mode isEqualToString:@"steam"]) return @"steam.exe";
    if ([mode isEqualToString:@"netease"]) return @"FeverGamesInstaller.exe";
    if ([mode isEqualToString:@"netease-game"]) return @"Sky.exe";
    return nil;
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
            if (delegate && !delegate.terminating) [NSApp terminate:nil];
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

- (BOOL)applicationShouldHandleReopen:(NSApplication *)sender
                    hasVisibleWindows:(BOOL)flag {
    (void)sender;
    (void)flag;
    [self activateWindowsProcess];
    return YES;
}

- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    (void)sender;
    self.terminating = YES;
    NSString *mode = self.launchArguments.firstObject;
    if ([mode isEqualToString:@"netease"] &&
        [self isWindowsModeRunning:@"netease-game"]) {
        // Sky asks FeverGames for its login ticket after its window appears.
        // Detach instead of killing the bridge so closing the launcher's Dock
        // icon cannot turn that late ticket hand-off into a fake network error.
        self.launchTask.terminationHandler = nil;
        self.launchTask = nil;
        return NSTerminateNow;
    }
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
