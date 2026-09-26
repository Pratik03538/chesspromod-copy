if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print(
            "\n[INFO] Stopped by user."
        )

        cv2.destroyAllWindows()
