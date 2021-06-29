import subprocess

def trykill(proc):
    try:
        proc.kill()
    except:
        pass


def main():
    # 1. start server subprocess
    # 2. connect session 1 to it
    # 3. send command
    # 4. assert result  # not AAA-like, I know
    # 5. change mode
    # 6. connect session 2 to it
    # 7. send command
    # 8. expect result

    server_proc = subprocess.Popen(
        ["python3", "main.py"],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    print('vlad1')
    session1_proc = subprocess.Popen(
        ['telnet', 'localhost', '1848'],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    print('vlad2')

    try:
        sresult1 = server_proc.stderr.read()
        print('vlad3')
        # x = session1_proc.communicate(b'asdf\r\nquit')
        session1_proc.stdin.write(b'asdf\r\n')
        print('vlad4')
        s1results = [
            session1_proc.stdout.readline()
            for _ in range(2)
        ]
        print('vlad5')
        xx = 0

    finally:
        trykill(server_proc)
        trykill(session1_proc)



    print('asdf')


if __name__ == '__main__':
    main()
