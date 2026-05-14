            if uploaded.name.endswith(".csv"):
                df = pd.read_csv(uploaded)
            else:
                # Try reading with header on row 3 (index 2) first — WFM tracker format
                df_test = pd.read_excel(uploaded, header=2)
                if "Barcode" in df_test.columns:
                    df = df_test
                    uploaded.seek(0)
                else:
                    # Fall back to row 1 headers
                    uploaded.seek(0)
                    df = pd.read_excel(uploaded)
                # Drop empty rows
                df = df.dropna(how="all")