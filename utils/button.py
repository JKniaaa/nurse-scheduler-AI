import io
import pandas as pd
import streamlit as st

def excel_download_button(df, filename="data.xlsx", label="Download as Excel"):
    """
    Display a Streamlit download button for a DataFrame as an Excel file.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    st.download_button(
        label=label,
        data=output.getvalue(),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    